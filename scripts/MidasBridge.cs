using System;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading.Tasks;
using System.ComponentModel.DataAnnotations;
using NinjaTrader.NinjaScript;
using System.Threading;
using System.Linq;
using NinjaTrader.Cbi;
using NinjaTrader.Data;

namespace NinjaTrader.NinjaScript.Indicators
{
    public class MidasBridge : Indicator
    {
        private TcpListener server;
        private bool isRunning;
        private Timer accountUpdateTimer;
        private double lastPnl = double.MinValue;
        private Account account;
        private int AccountPort = 36970;
        private string lastChartTime = DateTime.Now.ToString("o");
        private DateTime lastDepthUpdate = DateTime.MinValue;
        private EMA ema15; 
        private double currentBidVol = 0;
        private double currentAskVol = 0;
        private TcpClient pythonClient;
        private NetworkStream pythonStream;


        protected override void OnStateChange()
        {
            Print("BRIDGE STATE: " + State.ToString());
            if (State == State.SetDefaults)
            {
                Description = "Midas Engine Data Bridge";
                Name = "MidasBridge";
                Calculate = Calculate.OnPriceChange;
                IsOverlay = true;
                ServerPort = 36999; // Default to MES port
                TargetAccountName = "DEMO5611174";
            }
            else if (State == State.Configure)
            {
                // Add a 15-minute data series in the background (Index 1)
                AddDataSeries(BarsPeriodType.Minute, 15);

                // --- Account Audit ---
                foreach(Account a in Cbi.Account.All) { Print("AVAILABLE ACCOUNT: " + a.Name); }
                // -------------------

                Print("SEARCHING FOR: " + TargetAccountName);
                // Clean, case-insensitive search
                var allAccounts = Cbi.Account.All.ToList();

                account = allAccounts.FirstOrDefault(a => a.Name.Equals(TargetAccountName, StringComparison.OrdinalIgnoreCase));

                if (account != null) 
                {
                    Print("FOUND ACCOUNT: " + account.Name);
                    account.ExecutionUpdate += OnExecutionUpdate;
                }

                if (account == null)
                {
                    Print("MidasBridge ERROR: Could not find account " + TargetAccountName + "!");
                }
            }
            else if (State == State.DataLoaded)
            {
                // Initialize the 15-period EMA on the 15-minute chart
                ema15 = EMA(BarsArray[1], 15);

                server = new TcpListener(IPAddress.Any, ServerPort);
                server.Start();
                isRunning = true;
                Task.Run(() => ListenForPython());

                InitializePythonConnection();

                // Start the timer to send account updates
                accountUpdateTimer = new Timer(SendAccountUpdate, null, 0, 5000);
            }
            else if (State == State.Terminated)
            {
                if (account != null) account.ExecutionUpdate -= OnExecutionUpdate;
                isRunning = false;
                server?.Stop();
                accountUpdateTimer?.Dispose();
                pythonStream?.Dispose();
                pythonClient?.Close();
            }
        }

        private void SendAccountUpdate(object state)
        {
            Print("--- DEBUG START ---");
            
            if (account == null) return;

            if (System.Windows.Application.Current != null)
            {
                System.Windows.Application.Current.Dispatcher.BeginInvoke(new Action(() =>
                {
                    try {
                        // 2. Check Values
                        double currentPnl = account.Get(AccountItem.RealizedProfitLoss, Currency.UsDollar);
                        
                        double balance = account.Get(AccountItem.NetLiquidation, Currency.UsDollar);
                        if (balance == 0) balance = account.Get(AccountItem.CashValue, Currency.UsDollar);

                        Print(string.Format("2. Data Pulled - Balance: {0}, PnL: {1}", balance, currentPnl));

                        int currentPos = 0;
                        Position pos = account.Positions.FirstOrDefault(p => p.Instrument.MasterInstrument.Name == Instrument.MasterInstrument.Name);
                        if (pos != null) {
                            currentPos = pos.MarketPosition == MarketPosition.Long ? pos.Quantity : (pos.MarketPosition == MarketPosition.Short ? -pos.Quantity : 0);
                        }

                        // 3. Check JSON Construction
                        string json = "{" +
                            "\"LABEL\":\"ACCOUNT_UPDATE\"," +
                            "\"chart_time\":\"" + lastChartTime + "\"," +
                            "\"ACCOUNT_VALUE\":" + balance + "," +
                            "\"DAILY_PNL\":" + currentPnl + "," +
                            "\"CASH_VALUE\":" + balance + "," +
                            "\"POSITION_SYMBOL\":\"" + Instrument.MasterInstrument.Name + "\"," +
                            "\"POSITION_QUANTITY\":" + currentPos +
                        "}";
                        Print("3. JSON Created.");

                        // 4. Attempt Socket
                        SendDataToPython(json);
                    }
                    catch (Exception ex) {
                        Print("CRASH IN TIMER: " + ex.Message);
                    }
                }));
            }
        }

        private void InitializePythonConnection()
        {
            try
            {
                pythonClient = new TcpClient("127.0.0.1", AccountPort);
                pythonStream = pythonClient.GetStream();
            }
            catch (Exception)
            {
                // Silent fail on connect to avoid spam, will retry next tick
            }
        }

        private void SendDataToPython(string data)
        {
            Print("SENDING DATA TO PYTHON...");
            try
            {
                if (pythonClient == null || !pythonClient.Connected || pythonStream == null || !pythonStream.CanWrite)
                {
                    InitializePythonConnection();
                }

                if (pythonStream != null && pythonStream.CanWrite)
                {
                    byte[] bytes = Encoding.UTF8.GetBytes(data + "\n");
                    pythonStream.Write(bytes, 0, bytes.Length);
                }
            }
            catch (Exception ex)
            {
                Print("SOCKET ERROR: " + ex.Message);
                pythonStream?.Dispose();
                pythonClient?.Close();
                pythonClient = null;
                pythonStream = null;
            }
        }

        private void ListenForPython()
        {
            while (isRunning)
            {
                try
                {
                    if (server.Pending())
                    {
                        TcpClient client = server.AcceptTcpClient();
                        NetworkStream stream = client.GetStream();
                        
                        byte[] buffer = new byte[1024];
                        int bytesRead = stream.Read(buffer, 0, buffer.Length);
                        string request = Encoding.UTF8.GetString(buffer, 0, bytesRead);

                        if (request.Contains("GET_PRICE"))
                        {
                            string priceString = GetCurrentAsk().ToString();
                            string[] reqParts = request.Split('|');
                            string reqSymbol = reqParts.Length > 1 ? reqParts[1] : Instrument.MasterInstrument.Name;
                            string responseStr = $"HEARTBEAT|{reqSymbol}|{priceString}|{lastChartTime}";
                            byte[] response = Encoding.UTF8.GetBytes(responseStr);
                            stream.Write(response, 0, response.Length);
                        }
                        else if (request.Contains("PLACE_ORDER"))
                        {
                            Print("PLACE_ORDER command received: " + request);
                            string[] parts = request.Split('|');
                            if (parts.Length == 4)
                            {
                                string side = parts[1];
                                string symbol = parts[2];
                                int quantity = int.Parse(parts[3]);

                                if (account != null && symbol == Instrument.MasterInstrument.Name)
                                {
                                    // --- SURGICAL UPDATE: Handle SHORT action from Python Engine ---
                                    OrderAction action;
                                    if (side == "BUY")
                                    {
                                        action = OrderAction.Buy;
                                    }
                                    else if (side == "SHORT")
                                    {
                                        action = OrderAction.SellShort;
                                        Print("Midas: Executing SHORT order.");
                                    }
                                    else // Default to Sell for liquidating longs
                                    {
                                        action = OrderAction.Sell;
                                    }
                                    System.Windows.Application.Current.Dispatcher.BeginInvoke(new Action(() =>
                                    {
                                       Order myOrder = account.CreateOrder(Instrument, action, OrderType.Market, TimeInForce.Day, quantity, 0, 0, string.Empty, "MidasOrder", null);
                                       account.Submit(new[] { myOrder });
                                    }));
                                    Print($"Submitted {side} order for {quantity} {symbol}");
                                }
                                else
                                {
                                    Print("Order not placed. Account is null or symbol mismatch.");
                                }
                            }
                        }
                        client.Close();
                    }
                }
                catch (Exception e) { Print("ListenForPython Error: " + e.Message); }
            }
        }

        private void OnExecutionUpdate(object sender, ExecutionEventArgs e)
        {
            // Ensure we are only sending updates for the Midas account and it's a fill
            if (e.Execution.Order.Account == account && e.Execution.Order.OrderState == OrderState.Filled)
            {
                string side = e.Execution.Order.OrderAction == OrderAction.Buy ? "BUY" : "SELL";
                string json = "{" +
                    "\"LABEL\":\"ORDER_FILL\"," +
                    "\"chart_time\":\"" + e.Execution.Time.ToString("o") + "\"," +
                    "\"SYMBOL\":\"" + e.Execution.Instrument.MasterInstrument.Name + "\"," +
                    "\"QUANTITY\":" + e.Execution.Quantity + "," +
                    "\"PRICE\":" + e.Execution.Price + "," +
                    "\"SIDE\":\"" + side + "\"," +
                    "\"TIMESTAMP\":\"" + e.Execution.Time.ToString("o") + "\"" +
                "}";

                SendDataToPython(json);
            }
        }

        protected override void OnMarketData(NinjaTrader.Data.MarketDataEventArgs marketDataUpdate)
        {
            if (marketDataUpdate.MarketDataType == NinjaTrader.Data.MarketDataType.Bid)
            {
                currentBidVol = marketDataUpdate.Volume;
            }
            else if (marketDataUpdate.MarketDataType == NinjaTrader.Data.MarketDataType.Ask)
            {
                currentAskVol = marketDataUpdate.Volume;
            }
            // We only care about Last trades (the Tape)
            else if (marketDataUpdate.MarketDataType == NinjaTrader.Data.MarketDataType.Last)
            {
                if ((DateTime.Now - lastDepthUpdate).TotalMilliseconds < 250)
                    return;

                lastDepthUpdate = DateTime.Now;

                try
                {
                    lastChartTime = marketDataUpdate.Time.ToString("o");
                    
                    // Simple side detection logic
                    string side = marketDataUpdate.Price >= GetCurrentAsk() ? "BUY" : "SELL";
                    string emaValue = "null";
                    if (ema15 != null && ema15.IsValidDataPoint(0)) 
                    {
                        emaValue = ema15[0].ToString("F2");
                    }
                    
                    string json = "{" +
                        "\"LABEL\":\"TRADE\"," +
                        "\"chart_time\":\"" + lastChartTime + "\"," +
                        "\"SYMBOL\":\"" + Instrument.MasterInstrument.Name + "\"," +
                        "\"SIZE\":" + marketDataUpdate.Volume + "," +
                        "\"PRICE\":" + marketDataUpdate.Price + "," +
                        "\"SIDE\":\"" + side + "\"," +
                        "\"bid_vol\":" + currentBidVol + "," +
                        "\"ask_vol\":" + currentAskVol + "," +
                        "\"ema_15\":" + emaValue +
                    "}";

                    SendDataToPython(json);
                }
                catch (Exception ex)
                {
                    // Print("TAPE ERROR: " + ex.Message);
                }
            }
        }

        protected override void OnBarUpdate() 
        {
            if (CurrentBar >= 0)
                lastChartTime = Time[0].ToString("o");
        }

        // This is the magic block that adds the setting in the NT8 UI!
        [NinjaScriptProperty]
        [Range(1000, 65535)]
        [Display(Name="Server Port", Description="Port for this specific chart", Order=1, GroupName="Parameters")]
        public int ServerPort { get; set; }

        [NinjaScriptProperty]
        [Display(Name="Target Account", Description="Enter Playback101 or DEMO5611174", Order=2, GroupName="Parameters")]
        public string TargetAccountName { get; set; }
    }
}

#region NinjaScript generated code. Neither change nor remove.

namespace NinjaTrader.NinjaScript.Indicators
{
	public partial class Indicator : NinjaTrader.Gui.NinjaScript.IndicatorRenderBase
	{
		private MidasBridge[] cacheMidasBridge;
		public MidasBridge MidasBridge(int serverPort)
		{
			return MidasBridge(Input, serverPort);
		}

		public MidasBridge MidasBridge(ISeries<double> input, int serverPort)
		{
			if (cacheMidasBridge != null)
				for (int idx = 0; idx < cacheMidasBridge.Length; idx++)
					if (cacheMidasBridge[idx] != null && cacheMidasBridge[idx].ServerPort == serverPort && cacheMidasBridge[idx].EqualsInput(input))
						return cacheMidasBridge[idx];
			return CacheIndicator<MidasBridge>(new MidasBridge(){ ServerPort = serverPort }, input, ref cacheMidasBridge);
		}
	}
}

namespace NinjaTrader.NinjaScript.MarketAnalyzerColumns
{
	public partial class MarketAnalyzerColumn : MarketAnalyzerColumnBase
	{
		public Indicators.MidasBridge MidasBridge(int serverPort)
		{
			return indicator.MidasBridge(Input, serverPort);
		}

		public Indicators.MidasBridge MidasBridge(ISeries<double> input , int serverPort)
		{
			return indicator.MidasBridge(input, serverPort);
		}
	}
}

namespace NinjaTrader.NinjaScript.Strategies
{
	public partial class Strategy : NinjaTrader.Gui.NinjaScript.StrategyRenderBase
	{
		public Indicators.MidasBridge MidasBridge(int serverPort)
		{
			return indicator.MidasBridge(Input, serverPort);
		}

		public Indicators.MidasBridge MidasBridge(ISeries<double> input , int serverPort)
		{
			return indicator.MidasBridge(input, serverPort);
		}
	}
}

#endregion
