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

                Print("SEARCHING FOR: DEMO5611174");
                // Find the specific Demo account from your screenshot
                account = Cbi.Account.All.FirstOrDefault(a => a.Name == "DEMO5611174");

                if (account != null) Print("FOUND ACCOUNT: " + account.Name);

                if (account == null)
                {
                    Print("MidasBridge ERROR: Could not find account DEMO5611174!");
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
                account = Cbi.Account.All.FirstOrDefault(a => a.Name == "DEMO5611174");
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
                        double balance = account.Get(AccountItem.NetLiquidation, Currency.UsDollar);
                        Print(string.Format("2. Data Pulled - Balance: {0}, PnL: {1}", balance, currentPnl));

                        // 3. Check JSON Construction
                        string json = "{" +
                            "\"LABEL\":\"ACCOUNT_UPDATE\"," +
                            "\"ACCOUNT_VALUE\":" + balance + "," +
                            "\"DAILY_PNL\":" + currentPnl + "," +
                            "\"CASH_VALUE\":" + account.Get(AccountItem.CashValue, Currency.UsDollar) +
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
                            byte[] response = Encoding.UTF8.GetBytes(priceString);
                            stream.Write(response, 0, response.Length);
                        }
                        client.Close();
                    }
                }
                catch { /* Ignore */ }
            }
        }

        protected override void OnBarUpdate() { }

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
