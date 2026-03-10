using System;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading.Tasks;
using System.ComponentModel.DataAnnotations;
using NinjaTrader.NinjaScript;

namespace NinjaTrader.NinjaScript.Indicators
{
    public class MidasBridge : Indicator
    {
        private TcpListener server;
        private bool isRunning;

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = "Midas Engine Data Bridge";
                Name = "MidasBridge";
                Calculate = Calculate.OnPriceChange;
                IsOverlay = true;
                ServerPort = 36999; // Default to MES port
            }
            else if (State == State.DataLoaded)
            {
                server = new TcpListener(IPAddress.Any, ServerPort);
                server.Start();
                isRunning = true;
                Task.Run(() => ListenForPython());
            }
            else if (State == State.Terminated)
            {
                isRunning = false;
                server?.Stop();
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
