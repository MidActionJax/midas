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

    def reload_models(self):
        print("--- Hot Reloading AI Models ---")
        # Reload RL Model
        model_path = "models/midas_rl_model"
        if os.path.exists(f"{model_path}.zip"):
            try:
                new_rl = PPO.load(model_path)
                if new_rl:
                    self.rl_model = new_rl
                    print(f"--- RL Agent (AI Supervisor) reloaded successfully ---")
            except Exception as e:
                print(f"Error reloading RL model: {e}")
                
        # Reload Truth Engine
        from core.logic import brain
        if hasattr(brain, '_load_model'):
            brain.model = brain._load_model()
            
        import joblib
        truth_model_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'models', 'midas_truth_engine.joblib')
        if os.path.exists(truth_model_path):
            try:
                new_truth = joblib.load(truth_model_path)
                if new_truth:
                    logic.TRUTH_ENGINE = new_truth
                    print("--- Truth Engine reloaded successfully ---")
            except Exception as e:
                print(f"Error reloading Truth Engine: {e}")

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
                        is_long = pos_type == 'LONG'
                        
                        # --- TIGHTER MICRO-PROFIT PROTECTORS ---
                        points_profit = (current_price - entry_price) if is_long else (entry_price - current_price)
                        
                        # Estimate unrealized PnL manually for the logger 
                        multiplier = 5.0 if pos_symbol == 'MES' else 2.0
                        pos['unrealized_pnl'] = points_profit * multiplier * pos.get('size', 1)
                        
                        if 'dynamic_sl' not in pos:
                            pos['dynamic_sl'] = -4.0 # Default SL to 4 points as a safety net
                            
                        # The order here is important: check from highest profit target downwards.
                        if points_profit >= 2.75:
                            if pos['dynamic_sl'] < 2.00:
                                pos['dynamic_sl'] = 2.00
                                print(f"--- TRAILING STOP (STEP 2): {pos_symbol} SL moved to +2.00 points ---")
                        elif points_profit >= 1.75:
                            if pos['dynamic_sl'] < 1.00:
                                pos['dynamic_sl'] = 1.00
                                print(f"--- TRAILING STOP (STEP 1): {pos_symbol} SL moved to +1.00 point ---")
                        elif points_profit >= 1.25:
                            if pos['dynamic_sl'] < 0.25:
                                pos['dynamic_sl'] = 0.25
                                print(f"--- AUTO-BREAKEVEN: {pos_symbol} SL moved to +0.25 points ---")
                                 
                        hit_tp = points_profit >= 4.0 # Hard 4 points TP
                        hit_sl = points_profit <= pos['dynamic_sl']
                        
                        if hit_tp or hit_sl:
                            side = 'SELL' if is_long else 'BUY'
                            exit_reason = "TAKE PROFIT" if hit_tp else "STOP/TRAILING"
                            print(f"!!! SNIPER TRIGGERED ({exit_reason}): Closing {pos_symbol} at {current_price} !!!")
                            
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
                    
                    # --- FORCE IMMEDIATE APPEND TO CSV ---
                    try:
                        import csv
                        with open('trade_history.csv', 'a', newline='') as f:
                            writer = csv.DictWriter(f, fieldnames=[
                                'timestamp_id', 'symbol', 'type', 'price', 'size',
                                'ema_200_val', 'trend_dir', 'atr_volatility', 'session_context', 'whale_strength',
                                'ml_confidence', 'Whale_ID', 'user_decision', 'final_pnl', 'outcome_label', 'exit_reason'
                            ])
                            writer.writerow({
                                'timestamp_id': time.time(),
                                'symbol': pos.get('symbol', ''),
                                'type': pos.get('type', ''),
                                'price': pos.get('entry_price', 0),
                                'size': pos.get('size', 1),
                                'user_decision': 'APPROVED',
                                'final_pnl': final_pnl,
                                'outcome_label': 'WIN' if final_pnl > 0 else 'LOSS',
                                'exit_reason': 'Exit Executed'
                            })
                    except Exception as e:
                        print(f"Failed to append to CSV: {e}")

                    state.state_manager.add_pnl(final_pnl)
                    state.state_manager.remove_position(pos)
                    
                    # --- LIVE SCORECARD TRACKING ---
                    if not hasattr(state.state_manager, 'live_trades'):
                        state.state_manager.live_trades = 0
                        state.state_manager.live_wins = 0
                        
                    state.state_manager.live_trades += 1
                    if final_pnl > 0:
                        state.state_manager.live_wins += 1
                    state.state_manager.account_balance += final_pnl
                    
                    print(f"--- EXIT DETECTED: {final_pnl} ---")
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
                            
                        # --- SANITY CHECK FIREWALL ---
                        last_price = None
                        if len(state.state_manager.price_history.get(symbol, [])) > 0:
                            last_price = state.state_manager.price_history[symbol][-1]
                            
                        if last_price is not None and last_price > 0:
                            if abs(price - last_price) / last_price > 0.05:
                                print(f"❌ ANOMALY FIREWALL: Engine rejected cross-wired price for {symbol}. {last_price} -> {price}")
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
                                # --- CALC MARKET SYNC ---
                                correlation_score = 0.0
                                try:
                                    mes_hist = state.state_manager.price_history.get('MES', [])[-50:]
                                    mnq_hist = state.state_manager.price_history.get('MNQ', [])[-50:]
                                    if len(mes_hist) >= 20 and len(mnq_hist) >= 20:
                                        min_len = min(len(mes_hist), len(mnq_hist))
                                        df_corr = pd.DataFrame({'MES': mes_hist[-min_len:], 'MNQ': mnq_hist[-min_len:]})
                                        
                                        if df_corr['MES'].std() == 0 or df_corr['MNQ'].std() == 0:
                                            correlation_score = 1.0 # Perfect Sync fallback
                                        else:
                                            corr_val = df_corr['MES'].corr(df_corr['MNQ'])
                                            if pd.notna(corr_val):
                                                correlation_score = float(corr_val)
                                except Exception:
                                    pass

                                # --- DECISION TRACE ---
                                print(f"--- SIGNAL TRACE [{symbol}] ---")
                                
                                # 0. Core Strategy Filters (Trend & Volatility)
                                trend_pass = signal.get('trend_pass', True)
                                vol_pass = signal.get('volatility_pass', True)
                                
                                if not trend_pass:
                                    print(f"[CHECK] Trend Filter: [FAIL] (Market is {signal.get('trend', 'Unknown')})")
                                else:
                                    print(f"[CHECK] Trend Filter: [PASS]")
                                    
                                if not vol_pass:
                                    print(f"[CHECK] Volatility Filter: [FAIL] (ATR {signal.get('atr', 0.0):.2f})")
                                else:
                                    print(f"[CHECK] Volatility Filter: [PASS]")
                                
                                # 1. Market Regime Check
                                print(f"[CHECK] Market Regime: [PASS] ({chop_index:.2f})")

                                # 2. ML Confidence & Dynamic Thresholds
                                ml_pass = True
                                ml_val = signal.get('ml_confidence_value')
                                ml_threshold = 70.0
                                
                                if correlation_score > 0.90:
                                    ml_threshold = 60.0
                                    print(f"[ADJUSTMENT] High Sync detected! Lowering ML threshold to 60%.")

                                if ml_val is not None:
                                    if ml_val >= ml_threshold:
                                        print(f"[CHECK] ML Confidence: [PASS] ({ml_val:.2f}%)")
                                    else:
                                        print(f"[CHECK] ML Confidence: [FAIL] ({ml_val:.2f}%)")
                                        ml_pass = False
                                else:
                                    print(f"[CHECK] ML Confidence: [FAIL] (No ML score provided by strategy)")
                                    ml_pass = False

                                # 3. RL Supervisor
                                rl_pass = True
                                if self.rl_model:
                                    ai_action_str = {0: 'HOLD', 1: 'BUY', 2: 'SELL'}.get(ai_action, 'UNKNOWN')
                                    if signal['type'] == 'BUY_SIGNAL' and ai_action == 2:
                                        rl_pass = False
                                    elif signal['type'] == 'SELL_SIGNAL' and ai_action == 1:
                                        rl_pass = False
                                        
                                    rl_status = "PASS" if rl_pass else "FAIL"
                                    print(f"[CHECK] RL Supervisor: [{rl_status}] ({ai_action_str})")
                                else:
                                    print(f"[CHECK] RL Supervisor: [PASS] (N/A - No Model)")

                                # 4. No Shorting Firewall
                                no_short_pass = True
                                if signal['type'] == 'SELL_SIGNAL':
                                    no_short_pass = False
                                    print(f"[CHECK] No Shorting Firewall: [FAIL] (Reason: Long-Only Mode)")
                                else:
                                    print(f"[CHECK] No Shorting Firewall: [PASS]")

                                # FINAL DECISION
                                if not (trend_pass and vol_pass and ml_pass and rl_pass and no_short_pass):
                                    print("--- FINAL DECISION: [VETOED] ---")
                                    if not state.state_manager.dev_mode:
                                        continue
                                
                                print("--- FINAL DECISION: [EXECUTED] ---")
                                pending_signals = state.state_manager.get_pending_signals()
                                is_duplicate = any(s['price'] == signal['price'] and s['type'] == signal['type'] for s in pending_signals)
                                
                                if not is_duplicate:
                                    if 'context_data' in signal:
                                        logger.log_signal(signal, signal['context_data'], 'PENDING')
                                    state.state_manager.add_pending_signal(signal)
                                    reason = signal.get('reason', 'Unknown')
                                    confidence_score_str = signal.get('ml_confidence', f"{signal.get('confidence_score', 0):.2f}%" if 'confidence_score' in signal else 'N/A (DEV)')
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
