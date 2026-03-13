import threading
import time
import config
import os
import numpy as np
import pandas as pd
from adapters.paper_crypto import PaperCryptoAdapter
from adapters.paper_futures import PaperFuturesAdapter
from adapters.nt_futures import NTFuturesAdapter # Add this line
from core import state, logic, logger
from core.logic import TapeScanner
from stable_baselines3 import PPO

class MidasEngine(threading.Thread):
    def __init__(self, symbols):
        super().__init__(daemon=True)
        self._stop_event = threading.Event()
        self.symbols = symbols
        self.adapter = None
        self.last_trade_time = 0
        self.scanner = TapeScanner()
        self.price_buffer = {symbol: [] for symbol in symbols}
        self.last_bar_time = {symbol: time.time() for symbol in symbols}
        self.is_paused = False
        self.analysis_timer = 0
        
        # Load the RL Model (AI Supervisor)
        self.rl_model = None
        model_path = "models/midas_rl_model"
        if os.path.exists(f"{model_path}.zip"):
            try:
                self.rl_model = PPO.load(model_path)
                print(f"--- RL Agent (AI Supervisor) loaded successfully from {model_path}.zip ---")
            except Exception as e:
                print(f"Error loading RL model: {e}")
        else:
            print(f"--- Warning: RL model not found at {model_path}.zip. AI Supervisor disabled. ---")

    def flatten_all(self):
        print("!!! EMERGENCY KILL SWITCH ACTIVATED - FLATTENING ALL POSITIONS !!!")
        self.is_paused = True
        if not self.adapter:
            return
            
        tracked_positions = state.state_manager.get_active_positions()
        for pos in list(tracked_positions):
            if pos.get('exit_triggered'):
                continue
                
            pos_symbol = pos.get('symbol', '').upper()
            raw_type = pos.get('type', 'BUY').upper()
            pos_type = 'LONG' if 'BUY' in raw_type else 'SHORT'
            current_price = self.adapter.get_current_price(pos_symbol)
            
            if current_price:
                try:
                    if pos_type == 'LONG':
                        self.adapter.execute_sell(pos_symbol, pos.get('size', 1), current_price, signal_id=pos.get('signal_timestamp'))
                    else:
                        self.adapter.execute_buy(pos_symbol, pos.get('size', 1), current_price, signal_id=pos.get('signal_timestamp'))
                    pos['exit_triggered'] = True
                except Exception as ex:
                    print(f"Error executing kill switch exit: {ex}")

    def manage_positions(self):
        """Monitors active positions, updates PnL, and logs closed trades."""
        if not self.adapter:
            return

        try:
            live_positions = self.adapter.get_open_positions()
            tracked_positions = state.state_manager.get_active_positions()
            
            for pos in list(tracked_positions):
                # 🚨 THE GHOST EXORCIST 🚨
                # The NT adapter pushes raw duplicates ('BUY_SIGNAL') into our memory on every fill.
                # We ONLY want to track the rich position ('BUY') that we created in app.py.
                if 'SIGNAL' in pos.get('type', '').upper():
                    state.state_manager.remove_position(pos)
                    continue

                pos_symbol = pos.get('symbol', '').upper()
                raw_type = pos.get('type', 'BUY').upper()
                pos_type = 'LONG' if 'BUY' in raw_type else 'SHORT'
                
                # --- THE ULTIMATE FUZZY MATCH ---
                match = None
                for lp in live_positions:
                    lp_string = str(lp).upper() 
                    if pos_symbol in lp_string:
                        if pos_type == 'LONG' and ('LONG' in lp_string or 'BUY' in lp_string):
                            match = lp
                            break
                        elif pos_type == 'SHORT' and ('SHORT' in lp_string or 'SELL' in lp_string):
                            match = lp
                            break

                if match:
                    # 🚨 THE SAFETY CATCH 🚨
                    if pos.get('exit_triggered'):
                        continue

                    # --- POSITION IS OPEN: MONITOR FOR EXIT ---
                    pos['unrealized_pnl'] = match.get('pnl', match.get('unrealizedPnl', 0.0))
                    
                    current_price = self.adapter.get_current_price(pos_symbol)
                    entry_price = pos.get('entry_price')
                    
                    if current_price and entry_price:
                        target = 1.50 # Keep your 2-tick test value
                        is_long = pos_type == 'LONG'
                        
                        hit_tp = (is_long and current_price >= entry_price + target) or \
                                 (not is_long and current_price <= entry_price - target)
                        hit_sl = (is_long and current_price <= entry_price - target) or \
                                 (not is_long and current_price >= entry_price + target)
                                 
                        if hit_tp or hit_sl:
                            side = 'SELL' if is_long else 'BUY'
                            print(f"!!! SNIPER TRIGGERED: Closing {pos_symbol} at {current_price} !!!")
                            
                            try:
                                if side == 'SELL':
                                    self.adapter.execute_sell(pos_symbol, pos.get('size', 1), current_price, signal_id=pos.get('signal_timestamp'))
                                else:
                                    self.adapter.execute_buy(pos_symbol, pos.get('size', 1), current_price, signal_id=pos.get('signal_timestamp'))
                                
                                # Tag the position so it doesn't machine-gun NinjaTrader
                                pos['exit_triggered'] = True 
                            except Exception as ex:
                                print(f"Error executing auto-exit: {ex}")
                else:
                    # --- BULLETPROOF GRACE PERIOD ---
                    entry_time = pos.get('timestamp', time.time())
                    if time.time() - entry_time < 15:
                        continue 

                    final_pnl = pos.get('unrealized_pnl', 0.0)
                    sig_id = pos.get('signal_timestamp')
                    
                    if sig_id:
                        logger.log_trade_exit(sig_id, final_pnl, "Exit Detected")
                    
                    state.state_manager.add_pnl(final_pnl)
                    state.state_manager.remove_position(pos)
                    
                    print(f"--- TRADE CLOSED: {pos_symbol} | PnL: ${final_pnl} ---")
                    self.last_trade_time = time.time()
        except Exception as e:
            print(f"Error in manage_positions: {e}")

    def run(self):
        print(f"MidasEngine starting for symbols: {self.symbols}")
        while not self._stop_event.is_set():
            if state.state_manager.is_kill_switch_active:
                print('!!! CRITICAL: DAILY DRAWDOWN LIMIT REACHED. SHUTTING DOWN !!!')
                self.stop()
                break

            if self.adapter is None:
                if config.TRADING_MODE == 'NT_FUTURES':
                    print(f"Initializing NTFuturesAdapter on Account Port: {config.NT_PORT}")
                    self.adapter = NTFuturesAdapter(port=config.NT_PORT)
                    self.adapter.scanner = self.scanner
                elif config.TRADING_MODE == 'PAPER_FUTURES':
                    print("Initializing PaperFuturesAdapter...")
                    self.adapter = PaperFuturesAdapter()
                elif config.TRADING_MODE == 'PAPER_CRYPTO':
                    print("Initializing PaperCryptoAdapter...")
                    self.adapter = PaperCryptoAdapter()

            if self.adapter:
                try:
                    # --- Manage existing positions first ---
                    self.manage_positions()

                    if self.is_paused:
                        time.sleep(1)
                        continue

                    # --- Cooldown period after a trade ---
                    if time.time() - self.last_trade_time < 300: # 5-minute cooldown
                        time.sleep(1)
                        continue
                    
                    self.analysis_timer += 1
                    if self.analysis_timer < 5:
                        time.sleep(1)
                        continue
                    
                    self.analysis_timer = 0
                    
                    # --- Process each symbol ---
                    for symbol in self.symbols:
                        price = self.adapter.get_current_price(symbol)
                        if price is None:
                            print(f"Could not fetch price for {symbol}. Skipping analysis.")
                            continue
                            
                        print(f"HEARTBEAT: Price of {symbol} is {price}")
                        state.state_manager.add_price(symbol, price)
                        self.price_buffer[symbol].append(price)

                        # --- Bar Creation and Choppiness Index Calculation ---
                        current_time = time.time()
                        if current_time - self.last_bar_time[symbol] >= 60:
                            if self.price_buffer[symbol]:
                                # Create OHLC bar
                                bar = {
                                    'open': self.price_buffer[symbol][0],
                                    'high': max(self.price_buffer[symbol]),
                                    'low': min(self.price_buffer[symbol]),
                                    'close': self.price_buffer[symbol][-1]
                                }
                                state.state_manager.price_bars[symbol].append(bar)
                                state.state_manager.price_bars[symbol] = state.state_manager.price_bars[symbol][-200:]
                                
                                # Calculate Choppiness Index
                                if len(state.state_manager.price_bars[symbol]) >= 14:
                                    df = pd.DataFrame(state.state_manager.price_bars[symbol])
                                    chop_index = logic.calculate_choppiness_index(df)
                                    state.state_manager.current_chop_index = chop_index
                                    print(f"--- CHOP INDEX (MES): {chop_index:.2f} ---")

                                # Reset for next bar
                                self.price_buffer[symbol] = []
                                self.last_bar_time[symbol] = current_time


                        # Only perform deep analysis for the execution symbol (MES)
                        if symbol == 'MES':
                            market_depth = self.adapter.get_market_depth(symbol)
                            state.state_manager.set_market_data(symbol, market_depth)

                            chop_index = state.state_manager.current_chop_index

                            # --- AI SUPERVISOR (RL AGENT) ---
                            ai_action = 0 # 0=Hold, 1=Buy, 2=Sell
                            if self.rl_model and len(state.state_manager.price_history.get(symbol, [])) > 0:
                                current_price = state.state_manager.price_history[symbol][-1]
                                
                                ema_200 = current_price
                                if hasattr(self.adapter, 'current_features') and self.adapter.current_features.get('ema_200_val') is not None:
                                    ema_200 = self.adapter.current_features.get('ema_200_val')
                                else:
                                    calc_ema = logic.calculate_ema(state.state_manager.price_history[symbol], period=200)
                                    if calc_ema is not None:
                                        ema_200 = calc_ema

                                atr = logic.get_current_atr(state.state_manager.price_history[symbol])
                                whale_strength = float(len(state.state_manager.get_active_dominant_whales()))

                                obs = np.array([current_price, ema_200, chop_index, atr, whale_strength], dtype=np.float32)
                                action, _ = self.rl_model.predict(obs, deterministic=True)
                                ai_action = int(action)
                                action_map = {0: 'HOLD', 1: 'BUY', 2: 'SELL'}
                                print(f"--- AI RECOMMENDS: {action_map.get(ai_action, 'UNKNOWN')} ---")

                            # --- STRATEGY MANAGER ---
                            signal = None

                            if chop_index > 61.8:
                                # Ranging Market -> Mean Reversion
                                print(f"--- REGIME: RANGING ({chop_index:.2f}) -> Activating Mean Reversion Strategy ---")
                                signal = logic.analyze_mean_reversion(
                                    symbol,
                                    market_depth,
                                    state.state_manager.price_history.get(symbol, []),
                                    chop_index
                                )
                            elif chop_index < 38.2:
                                # Trending Market -> Breakout
                                print(f"--- REGIME: TRENDING ({chop_index:.2f}) -> Activating Breakout Strategy ---")
                                signal = logic.analyze_breakout(
                                    symbol,
                                    market_depth,
                                    state.state_manager.price_history.get(symbol, []),
                                    chop_index
                                )
                            else:  # 38.2 <= chop_index <= 61.8
                                # Standard/Choppy Market -> Iceberg
                                print(f"--- REGIME: STANDARD ({chop_index:.2f}) -> Activating Iceberg Strategy ---")
                                signal = logic.analyze_order_book(
                                    symbol, market_depth, state.state_manager.price_history, self.adapter
                                )

                            if signal:
                                # --- AI VETO LOGIC ---
                                vetoed = False
                                if self.rl_model:
                                    if signal['type'] == 'BUY_SIGNAL' and ai_action == 2:
                                        print("!!! AI VETO: RL Agent disagrees with Strategy Manager !!!")
                                        vetoed = True
                                    elif signal['type'] == 'SELL_SIGNAL' and ai_action == 1:
                                        print("!!! AI VETO: RL Agent disagrees with Strategy Manager !!!")
                                        vetoed = True

                                if not vetoed:
                                    pending_signals = state.state_manager.get_pending_signals()
                                    is_duplicate = any(s['price'] == signal['price'] and s['type'] == signal['type'] for s in pending_signals)
                                    
                                    if not is_duplicate:
                                        state.state_manager.add_pending_signal(signal)
                                        reason = signal.get('reason', 'Unknown')
                                        confidence_score_str = f"{signal.get('confidence_score', 0):.2f}%" if 'confidence_score' in signal else 'N/A (DEV)'
                                        print(f"!!! NEW SIGNAL [{reason}]: {signal['type']} at {signal['price']} for {signal['size']} with {confidence_score_str} confidence!!!")

                except Exception as e:
                    print(f"Error in engine loop: {e}")
            
            time.sleep(1)
        
        print("MidasEngine stopped.")

    def stop(self):
        print("Stopping MidasEngine...")
        self._stop_event.set()

engine_thread = None

def start_engine():
    global engine_thread
    import config 
    
    if engine_thread is None or not engine_thread.is_alive():
        symbols_to_trade = []
        # UPDATE THIS LINE to include NT_FUTURES
        if config.TRADING_MODE in ['PAPER_FUTURES', 'NT_FUTURES']: 
            symbols_to_trade = ['MES', 'MNQ']
            config.TRADING_SYMBOL = 'MES'
        else: # PAPER_CRYPTO or LIVE_CRYPTO
            symbols_to_trade = ['BTC/USDT']
            config.TRADING_SYMBOL = 'BTC/USDT'

        print(f"Engine starting in mode: {config.TRADING_MODE} for {symbols_to_trade}")
        engine_thread = MidasEngine(symbols_to_trade)
        engine_thread.start()

def stop_engine():
    global engine_thread
    if engine_thread and engine_thread.is_alive():
        # Safety Check: Only call disconnect if the adapter actually exists
        if engine_thread.adapter and hasattr(engine_thread.adapter, 'ib'):
            try:
                print("Disconnecting from IB...")
                engine_thread.adapter.ib.disconnect()
            except Exception as e:
                print(f"Error during disconnect: {e}")
        
        engine_thread.stop()
        engine_thread.join()
        engine_thread = None
        state.state_manager.save_price_history()
        print("MidasEngine stopped and price history saved.")
