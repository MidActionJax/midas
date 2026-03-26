using System;
using System.IO;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.NinjaScript;

namespace NinjaTrader.NinjaScript.Indicators
{
	public class Level2Vacuum : Indicator
	{
		private StreamWriter csvWriter;
		private string filePath;

		protected override void OnStateChange()
		{
			if (State == State.Historical)
			{
				// This creates the CSV file on your desktop
				string desktopPath = Environment.GetFolderPath(Environment.SpecialFolder.Desktop);
				filePath = Path.Combine(desktopPath, $"MES_Level2_Dump_{DateTime.Now:yyyyMMdd_HHmmss}.csv");
				
				csvWriter = new StreamWriter(filePath, true);
				// Write the Headers
				csvWriter.WriteLine("Timestamp,Side,Position,Price,Volume");
			}
			else if (State == State.Terminated)
			{
				// Cleanly close the file when you stop the replay
				if (csvWriter != null)
				{
					csvWriter.Close();
					csvWriter.Dispose();
				}
			}
		}

		protected override void OnMarketDepth(MarketDepthEventArgs marketDepthUpdate)
		{
			// We only want to record data during the live replay, not historical loading
			if (State == State.Historical || State == State.Realtime)
			{
				// Format: Side (Ask=0, Bid=1)
				string side = marketDepthUpdate.MarketDataType == MarketDataType.Ask ? "Ask" : "Bid";
				
				// Build the exact row of data
				string dataRow = string.Format("{0},{1},{2},{3},{4}", 
					marketDepthUpdate.Time.ToString("yyyy-MM-dd HH:mm:ss.fff"), 
					side, 
					marketDepthUpdate.Position, 
					marketDepthUpdate.Price, 
					marketDepthUpdate.Volume);

				// Instantly write it to the CSV
				csvWriter.WriteLine(dataRow);
			}
		}
	}
}