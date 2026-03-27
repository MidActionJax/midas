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
            }
            else if (State == State.Configure)
            {
                // --- Account Audit ---
                foreach(Account a in Cbi.Account.All) { Print("AVAILABLE ACCOUNT: " + a.Name); }
                // -------------------

                Print("SEARCHING FOR: DEMO5611174 or Playback101");
                // Find the specific Demo account or Playback account
                account = Cbi.Account.All.FirstOrDefault(a => a.Name == "DEMO5611174" || a.Name == "Playback101");

                if (account != null) 
                {
                    Print("FOUND ACCOUNT: " + account.Name);
                    account.ExecutionUpdate += OnExecutionUpdate;
                }

                if (account == null)
                {
                    Print("MidasBridge ERROR: Could not find account DEMO5611174 or Playback101!");
                }
            }
            else if (State == State.DataLoaded)
            {
                server = new TcpListener(IPAddress.Any, ServerPort);
                server.Start();
                isRunning = true;
                Task.Run(() => ListenForPython());

                // Start the timer to send account updates
                accountUpdateTimer = new Timer(SendAccountUpdate, null, 0, 5000);
            }
            else if (State == State.Terminated)
            {
                if (account != null) account.ExecutionUpdate -= OnExecutionUpdate;
                isRunning = false;
                server?.Stop();
                accountUpdateTimer?.Dispose();
            }
        }

        private void SendAccountUpdate(object state)
        {
            Print("--- DEBUG START ---");
            
            // 1. Check Account
            if (account == null) {
                account = Cbi.Account.All.FirstOrDefault(a => a.Name == "DEMO5611174" || a.Name == "Playback101");
                Print("1. Searching for Account... " + (account != null ? "FOUND" : "NOT FOUND"));
            }
            
            if (account == null) return;

            if (System.Windows.Application.Current != null)
            {
                System.Windows.Application.Current.Dispatcher.Invoke(() =>
                {
                    try {
                        // 2. Check Values
                        double currentPnl = account.Get(AccountItem.RealizedProfitLoss, Currency.UsDollar);
                        double balance = account.Get(AccountItem.CashValue, Currency.UsDollar);
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
                            "\"CASH_VALUE\":" + account.Get(AccountItem.CashValue, Currency.UsDollar) + "," +
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
                });
            }
        }

        private void SendDataToPython(string data)
        {
            Print("SENDING DATA TO PYTHON...");
            try
            {
                using (TcpClient client = new TcpClient("127.0.0.1", AccountPort))
                using (NetworkStream stream = client.GetStream())
                {
                    byte[] bytes = Encoding.UTF8.GetBytes(data);
                    stream.Write(bytes, 0, bytes.Length);
                }
            }
            catch (Exception ex)
            {
                Print("SOCKET ERROR: " + ex.Message);
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
                                    System.Windows.Application.Current.Dispatcher.Invoke(() =>
                                    {
                                       Order myOrder = account.CreateOrder(Instrument, action, OrderType.Market, TimeInForce.Day, quantity, 0, 0, string.Empty, "MidasOrder", null);
                                       account.Submit(new[] { myOrder });
                                    });
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
            // We only care about Last trades (the Tape)
            if (marketDataUpdate.MarketDataType == NinjaTrader.Data.MarketDataType.Last)
            {
                if ((DateTime.Now - lastDepthUpdate).TotalMilliseconds < 250)
                    return;

                lastDepthUpdate = DateTime.Now;

                try
                {
                    lastChartTime = marketDataUpdate.Time.ToString("o");
                    
                    // Simple side detection logic
                    string side = marketDataUpdate.Price >= GetCurrentAsk() ? "BUY" : "SELL";
                    
                    string json = "{" +
                        "\"LABEL\":\"TRADE\"," +
                        "\"chart_time\":\"" + lastChartTime + "\"," +
                        "\"SYMBOL\":\"" + Instrument.MasterInstrument.Name + "\"," +
                        "\"SIZE\":" + marketDataUpdate.Volume + "," +
                        "\"PRICE\":" + marketDataUpdate.Price + "," +
                        "\"SIDE\":\"" + side + "\"" +
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
