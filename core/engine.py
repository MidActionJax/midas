import threading
import time
import config
import os
import math
import numpy as np
import pandas as pd
from adapters.paper_crypto import PaperCryptoAdapter
from adapters.paper_futures import PaperFuturesAdapter
from adapters.nt_futures import NTFuturesAdapter # Add this line
from core import state, logic, logger
from core.logic import TapeScanner
from stable_baselines3 import PPO

def log_to_both(message):
    print(message)
    state.state_manager.add_to_blackbox(message)

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
        self._is_executing = False
        
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
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        truth_model_long_path = os.path.join(base_dir, 'models', 'midas_brain.pkl')
        truth_model_short_path = os.path.join(base_dir, 'models', 'midas_brain_short.pkl')
        
        if os.path.exists(truth_model_long_path):
            try:
                new_truth_long = joblib.load(truth_model_long_path)
                if new_truth_long:
                    logic.TRUTH_ENGINE_LONG = new_truth_long
                    print("--- Dual-Core Engine: LONG Brain reloaded successfully ---")
            except Exception as e:
                print(f"Error reloading LONG Brain: {e}")

        if os.path.exists(truth_model_short_path):
            try:
                new_truth_short = joblib.load(truth_model_short_path)
                if new_truth_short:
                    logic.TRUTH_ENGINE_SHORT = new_truth_short
                    print("--- Dual-Core Engine: SHORT Brain reloaded successfully ---")
            except Exception as e:
                print(f"Error reloading SHORT Brain: {e}")

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
                    # --- HARD GUARD ---
                    live_nt = getattr(state.state_manager, 'live_nt_positions', {})
                    current_pos = None
                    for k, v in live_nt.items():
                        if pos_symbol in k:
                            current_pos = v
                            break
                            
                    if current_pos is None:
                        current_pos = pos.get('size', 1) if pos_type == 'LONG' else -pos.get('size', 1)
                        
                    exit_size = abs(current_pos)
                    
                    if pos_type == 'LONG':
                        if current_pos <= 0:
                            print(f"!!! HARD GUARD: Blocked Kill Switch SELL for {pos_symbol} (Broker reports Flat/Short) !!!")
                            pos['exit_triggered'] = True
                        else:
                            self.adapter.execute_sell(pos_symbol, exit_size, current_price, signal_id=pos.get('signal_timestamp'))
                            pos['exit_triggered'] = True
                    else:
                        if current_pos >= 0:
                            print(f"!!! HARD GUARD: Blocked Kill Switch BUY for {pos_symbol} (Broker reports Flat/Long) !!!")
                            pos['exit_triggered'] = True
                        else:
                            self.adapter.execute_buy(pos_symbol, exit_size, current_price, signal_id=pos.get('signal_timestamp'))
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
            
            live_nt = getattr(state.state_manager, 'live_nt_positions', {})
            for sym, net_pos in live_nt.items():
                if net_pos != 0:
                    is_tracked = any(p.get('symbol') in sym for p in tracked_positions)
                    if not is_tracked:
                        # 🛡️ GHOST ADOPTION SHIELD: Ignore straggling NT balances for 15s after an exit
                        if state.state_manager.get_current_time().timestamp() - self.last_trade_time > 15:
                            current_price = self.adapter.get_current_price(sym)
                            adopted_pos = {
                                'symbol': 'MES' if 'MES' in sym else ('MNQ' if 'MNQ' in sym else sym),
                                'type': 'BUY' if net_pos > 0 else 'SELL',
                                'size': abs(net_pos),
                                'entry_price': current_price,
                                'timestamp': time.time(),
                                'signal_timestamp': time.time(),
                                'dynamic_sl': -3.0
                            }
                            state.state_manager.add_position(adopted_pos)
                            tracked_positions.append(adopted_pos)

            seen_signatures = set()
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
                
                # --- DEAD SOCKET SWEEPER ---
                # If the bot triggered an exit, track the real-world time.
                if pos.get('exit_triggered'):
                    if 'exit_real_timestamp' not in pos:
                        pos['exit_real_timestamp'] = time.time()
                    # If 10 real seconds have passed and the position is still in memory, the socket crashed. Force clear it.
                    elif time.time() - pos['exit_real_timestamp'] > 10:
                        print(f"--- 🧹 ORPHAN SWEEPER: Broker connection lost/timed out. Force clearing {pos_symbol} ---")
                        try:
                            state.state_manager.active_positions.remove(pos)
                        except ValueError:
                            pass
                        if hasattr(state.state_manager, 'live_nt_positions'):
                            state.state_manager.live_nt_positions[pos_symbol] = 0
                        continue

                # --- THE ULTIMATE FUZZY MATCH ---
                match = None
                
                live_nt_qty = getattr(state.state_manager, 'live_nt_positions', {}).get(pos_symbol, None)
                
                if live_nt_qty is not None and config.TRADING_MODE == 'NT_FUTURES':
                    if pos_type == 'LONG' and live_nt_qty > 0:
                        match = {'size': live_nt_qty, 'side': 'LONG'}
                    elif pos_type == 'SHORT' and live_nt_qty < 0:
                        match = {'size': abs(live_nt_qty), 'side': 'SHORT'}
                else:
                    for lp in live_positions:
                        lp_string = str(lp).upper() 
                        if pos_symbol in lp_string:
                            if pos_type == 'LONG' and ('LONG' in lp_string or 'BUY' in lp_string):
                                match = lp
                                break
                            elif pos_type == 'SHORT' and ('SHORT' in lp_string or 'SELL' in lp_string):
                                match = lp
                                break

                # --- VIRTUAL MATCH GRACE PERIOD ---
                # If NT8 hasn't reported the fill yet, use REAL CPU time (not Replay time) to wait for network latency
                if match is None and abs(time.time() - pos.get('real_timestamp', time.time())) < 15 and not pos.get('exit_triggered'):
                    match = {'size': pos.get('size', 1), 'side': pos_type}

                # Identify and remove any positions that share the exact same entry_price and signal_timestamp
                sig = (pos.get('signal_timestamp'), pos.get('entry_price'))
                if sig in seen_signatures:
                    if match:
                        print(f"[🛡️ DE-DUP] Blocking ghost position for signal {pos.get('signal_timestamp')}.")
                        state.state_manager.remove_position(pos)
                    continue
                seen_signatures.add(sig)

                if match:
                    real_entry = match.get('averagePrice', match.get('avgPrice'))
                    if real_entry and float(real_entry) > 0:
                        pos['entry_price'] = float(real_entry)

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
                        pos['max_profit'] = max(pos.get('max_profit', points_profit), points_profit)
                        
                        # Calculate ATR continuously for dynamic trailing
                        price_hist = state.state_manager.price_history.get(pos_symbol, [])
                        current_atr = logic.get_current_atr(price_hist) if price_hist else 2.0

                        if 'dynamic_sl' not in pos:
                            if state.state_manager.is_concrete_wet:
                                pos['dynamic_sl'] = max(-6.0, - (1.5 * current_atr))
                            else:
                                pos['dynamic_sl'] = -2.0
                            
                        # --- DIAGNOSTIC HEARTBEAT LOG ---
                        current_time = time.time()
                        if current_time - pos.get('last_pnl_log_time', 0) >= 5:
                            log_to_both(f"💓 [HEARTBEAT] {pos_symbol} {pos_type} | Profit: {points_profit:.2f} pts | SL: {pos.get('dynamic_sl', -1.0):.2f}")
                            pos['last_pnl_log_time'] = current_time

                        # --- TASK 2: TIERED RATCHET (GEARS) ---
                        if pos['max_profit'] > 5.0 * current_atr:
                            new_sl = pos['max_profit'] - (3.0 * current_atr)
                            if new_sl > pos['dynamic_sl']:
                                pos['dynamic_sl'] = new_sl
                                log_to_both(f"--- GEAR 3 RATCHET: {pos_symbol} SL moved to +{new_sl:.2f} (ATR: {current_atr:.2f}) ---")
                        elif pos['max_profit'] > 3.0 * current_atr:
                            new_sl = pos['max_profit'] - (1.5 * current_atr)
                            if new_sl > pos['dynamic_sl']:
                                pos['dynamic_sl'] = new_sl
                                log_to_both(f"--- GEAR 2 RATCHET: {pos_symbol} SL moved to +{new_sl:.2f} (ATR: {current_atr:.2f}) ---")
                        elif pos['max_profit'] > 1.5 * current_atr:
                            new_sl = 0.25
                            if new_sl > pos['dynamic_sl']:
                                pos['dynamic_sl'] = new_sl
                                log_to_both(f"--- GEAR 1 AUTO-BREAKEVEN: {pos_symbol} SL moved to +{new_sl:.2f} (ATR: {current_atr:.2f}) ---")
                                 
                        # Remove the hard ceiling
                        hit_tp = False 
                        hit_sl = points_profit <= pos['dynamic_sl']
                        
                        # --- WALL-BANGER TAKE PROFIT ---
                        if points_profit >= 3.5:
                            market_depth = state.state_manager.get_market_data(pos_symbol)
                            if market_depth:
                                floor_price, floor_vol, ceil_price, ceil_vol = logic.get_macro_box(market_depth, current_price)
                                dynamic_wall = logic.get_dynamic_wall_threshold(market_depth)
                                if is_long and (ceil_price - current_price) <= 1.0 and ceil_vol >= dynamic_wall:
                                    hit_tp = True
                                    log_to_both(f"--- WALL-BANGER TP: {pos_symbol} LONG hit Ceiling Wall at {ceil_price} ---")
                                elif not is_long and (current_price - floor_price) <= 1.0 and floor_vol >= dynamic_wall:
                                    hit_tp = True
                                    log_to_both(f"--- WALL-BANGER TP: {pos_symbol} SHORT hit Floor Wall at {floor_price} ---")

                        # --- EMA TREND-RIDER ---
                        ema_15 = None
                        riding_trend = False
                        market_data = state.state_manager.get_market_data(pos_symbol)
                        if market_data and 'ema_15' in market_data:
                            ema_15 = market_data['ema_15']
                        if ema_15 is None and hasattr(self.adapter, 'current_features'):
                            ema_15 = self.adapter.current_features.get(f'ema_15_{pos_symbol.lower()}')
                            
                        if ema_15 is not None:
                            riding_trend = (is_long and current_price >= ema_15) or (not is_long and current_price <= ema_15)

                        # --- TASK 1: 45-SECOND KILL SWITCH ---
                        current_market_ts = state.state_manager.get_current_time().timestamp()
                        time_open = current_market_ts - pos.get('timestamp', current_market_ts)
                        hit_time_kill = time_open >= 45 and points_profit <= 0 and not riding_trend
                        
                        # --- STAGNATION TIGHTENER ---
                        if time_open > 120 and not riding_trend:
                            new_sl = pos['max_profit'] - 1.5
                            if new_sl > pos['dynamic_sl']:
                                pos['dynamic_sl'] = new_sl
                                log_to_both(f"--- STAGNATION TIGHTENER: {pos_symbol} SL moved to {new_sl:.2f} ---")
                        
                        stagnation_signal = logic.analyze_stagnation_exit(pos_symbol, current_price, pos)
                        if riding_trend:
                            stagnation_signal = None

                        if hit_tp or hit_sl or hit_time_kill or stagnation_signal:
                            if pos.get('exit_triggered'):
                                pass  # Exit order already sent. Waiting for broker confirmation.
                            else:
                                side = 'SELL' if is_long else 'BUY'
                                if hit_tp:
                                    exit_reason = "TAKE PROFIT"
                                elif hit_time_kill:
                                    exit_reason = "45-SECOND EJECT"
                                    log_to_both("!!! EJECT: 45-second rule triggered. Trade stagnant/reversing. !!!")
                                elif stagnation_signal:
                                    exit_reason = "STAGNATION DECAY"
                                else:
                                    exit_reason = "STOP/TRAILING"
                                    
                                log_to_both(f"!!! SNIPER TRIGGERED ({exit_reason}): Closing {pos_symbol} at {current_price} !!!")
                                
                                # Tag the position IMMEDIATELY to prevent machine-gunning NinjaTrader on socket drop
                                pos['exit_triggered'] = True
                                pos['exit_time'] = time.time()
                                self.last_trade_time = state.state_manager.get_current_time().timestamp()
                                
                                try:
                                    # --- HARD GUARD: Right before executing exit PLACE_ORDER ---
                                    current_pos = None
                                    
                                    # 1. Trust match from get_open_positions() if possible
                                    if isinstance(match, dict):
                                        for key in ['position', 'quantity', 'pos', 'size']:
                                            if key in match:
                                                try:
                                                    val = int(match[key])
                                                    match_str = str(match).upper()
                                                    if 'SHORT' in match_str or 'SELL' in match_str or val < 0:
                                                        current_pos = -abs(val)
                                                    else:
                                                        current_pos = abs(val)
                                                    break
                                                except (ValueError, TypeError):
                                                    continue
                                                    
                                    # 2. Fallback to live_nt_positions
                                    if current_pos is None:
                                        for k, v in getattr(state.state_manager, 'live_nt_positions', {}).items():
                                            if pos_symbol in k:
                                                current_pos = v
                                                break
                                                
                                    # 3. Fallback to tracked position size
                                    if current_pos is None:
                                        current_pos = pos.get('size', 1) if is_long else -pos.get('size', 1)
    
                                    exit_size = abs(current_pos) if current_pos != 0 else pos.get('size', 1)
                                    
                                    if side == 'BUY' and current_pos >= 0:
                                        log_to_both(f"!!! HARD GUARD: Blocked Exit BUY for {pos_symbol} (Target is Flat/Long) !!!")
                                        pos['exit_triggered'] = False
                                        pos.pop('exit_time', None)
                                    elif side == 'SELL' and current_pos <= 0:
                                        log_to_both(f"!!! HARD GUARD: Blocked Exit SELL for {pos_symbol} (Target is Flat/Short) !!!")
                                        pos['exit_triggered'] = False
                                        pos.pop('exit_time', None)
                                    else:
                                        if side == 'SELL':
                                            self.adapter.execute_sell(pos_symbol, exit_size, current_price, signal_id=pos.get('signal_timestamp'))
                                        else:
                                            self.adapter.execute_buy(pos_symbol, exit_size, current_price, signal_id=pos.get('signal_timestamp'))
                                except Exception as ex:
                                    print(f"Error executing auto-exit: {ex}")
                                    pos['exit_triggered'] = False
                                    pos.pop('exit_time', None)
                else:
                    # --- POSITION FLAT/CLOSED FLOW ---
                    current_time = state.state_manager.get_current_time().timestamp()

                    # --- BULLETPROOF GRACE PERIOD ---
                    # Use real CPU time for network syncing
                    if abs(time.time() - pos.get('real_timestamp', time.time())) < 15 and not pos.get('exit_triggered'):
                        if time.time() - pos.get('last_match_fail_time', 0) >= 5:
                            print(f"[⏳ SYNC WAIT] NT8 hasn't confirmed {pos_symbol} order yet. Waiting...")
                            pos['last_match_fail_time'] = time.time()
                        continue 

                    if pos.get('exit_triggered') and current_time - pos.get('last_match_fail_time', 0) >= 5:
                        print(f"[✅ BROKER CONFIRMATION] NT8 confirms {pos_symbol} is flat. Finalizing exit.")
                        pos['last_match_fail_time'] = current_time

                    final_pnl = pos.get('unrealized_pnl', 0.0)
                    
                    sig_id = pos.get('signal_id')
                    if not sig_id:
                        sig_id = pos.get('signal_timestamp')
                    
                    if sig_id:
                        # PnL Protection: Ensure final_pnl is only added once per unique signal_timestamp
                        if state.state_manager.is_signal_closed(sig_id):
                            state.state_manager.remove_position(pos)
                            continue
                        state.state_manager.mark_signal_closed(sig_id)
                        
                        try:
                            logger.log_trade_exit(sig_id, final_pnl, "Exit Detected")
                        except Exception as e:
                            print(f"Logger warning: {e}")
                        
                        # --- EXIT TRIGGER: WRITE LOG ---
                        sig_id_str = str(sig_id)
                        if sig_id_str in state.state_manager.active_trade_logs:
                            log_lines = state.state_manager.active_trade_logs.pop(sig_id_str)
                            log_lines.append(f"FINAL PNL: {final_pnl}")
                            
                            outcome = "WIN" if final_pnl > 0 else "LOSS"
                            os.makedirs(os.path.join("logs", "post_mortem"), exist_ok=True)
                            log_path = os.path.join("logs", "post_mortem", f"trade_{sig_id_str}_{outcome}.txt")
                            try:
                                with open(log_path, "w", encoding="utf-8") as lf:
                                    for line in log_lines:
                                        lf.write(f"{line}\n")
                                print(f"--- POST-MORTEM LOG SAVED: {log_path} ---")
                            except Exception as e:
                                print(f"Error saving post-mortem log: {e}")
                    
                    # --- FORCE IMMEDIATE APPEND TO CSV ---
                    try:
                        import csv
                        with open('trade_history.csv', 'a', newline='') as f:
                            writer = csv.DictWriter(f, fieldnames=[
                                'timestamp_id', 'symbol', 'type', 'price', 'size',
                                'ema_200_val', 'trend_dir', 'atr_volatility', 'session_context', 'whale_strength',
                                'ml_confidence', 'Whale_ID', 'user_decision', 'final_pnl', 'outcome_label', 'exit_reason',
                                'signal_id'
                            ])
                            writer.writerow({
                                'signal_id': pos.get('signal_id', ''),
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
                    with state.state_manager._lock:
                        if not hasattr(state.state_manager, 'live_trades'):
                            state.state_manager.live_trades = 0
                            state.state_manager.live_wins = 0
                            
                        state.state_manager.live_trades += 1
                        if final_pnl > 0:
                            state.state_manager.live_wins += 1
                            state.state_manager.consecutive_losses = 0
                            state.state_manager.consecutive_loss_pnl = 0.0
                        elif final_pnl < 0:
                            state.state_manager.consecutive_losses += 1
                            state.state_manager.consecutive_loss_pnl += final_pnl
                            if state.state_manager.consecutive_loss_pnl <= -50.0 or state.state_manager.consecutive_losses >= 5:
                                state.state_manager.time_out_until = time.time() + 900
                                log_to_both("!!! 15-MINUTE SPEED BUMP ACTIVATED (Drawdown limit reached) !!!")
                                state.state_manager.consecutive_losses = 0
                                state.state_manager.consecutive_loss_pnl = 0.0
                                
                        state.state_manager.account_balance += final_pnl
                    
                    log_to_both(f"--- EXIT DETECTED: {final_pnl} ---")
                    self.last_trade_time = state.state_manager.get_current_time().timestamp()
        except Exception as e:
            print(f"Error in manage_positions: {e}")

    def run(self):
        print(f"MidasEngine starting for symbols: {self.symbols}")
        while not self._stop_event.is_set():
            start_time = time.time()
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
                    # --- REVERSAL TIMEOUT TRAP ---
                    if getattr(state.state_manager, 'is_reversing', False):
                        reversal_start = getattr(state.state_manager, 'reversal_start_time', None)
                        if reversal_start and time.time() - reversal_start > 5.0:
                            print("!!! REVERSAL TIMEOUT: 5.0s elapsed. Force-resetting is_reversing to False !!!")
                            state.state_manager.is_reversing = False
                            state.state_manager.reversal_start_time = None

                    # --- Manage existing positions first ---
                    self.manage_positions()

                    # --- GLOBAL CIRCUIT BREAKER ---
                    if state.state_manager.daily_pnl <= state.state_manager.MAX_DAILY_LOSS and not state.state_manager.circuit_breaker_tripped:
                        state.state_manager.circuit_breaker_tripped = True
                        print("🛑 CIRCUIT BREAKER TRIPPED: Max Daily Loss Reached. Engine disabled for the day.")
                        self.flatten_all()

                    if self.is_paused:
                        time.sleep(1)
                        continue

                    state.state_manager.cleanup_pending_signals()

                    # --- Cooldown period after a trade ---
                    in_cooldown = False
                    if state.state_manager.get_current_time().timestamp() - self.last_trade_time < 300: # 5-minute cooldown
                        in_cooldown = True

                    # --- 60-Minute Time-Out Check ---
                    in_timeout = False
                    if getattr(state.state_manager, 'time_out_until', None) is not None and time.time() < state.state_manager.time_out_until:
                        in_timeout = True
                    
                    if not hasattr(self, '_last_scan_time'):
                        self._last_scan_time = 0
                    current_loop_time = time.time()
                    if current_loop_time - self._last_scan_time < 1.0:
                        time.sleep(0.05)
                        continue
                    self._last_scan_time = current_loop_time

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

                        if last_price is not None and symbol == 'MES':
                            # Extract the volume of the last trade from the adapter
                            volume = getattr(self.adapter, 'last_trade_volume', 1.0)
                            state.state_manager.update_cvd(price, last_price, volume)

                        ema_15 = None
                        if hasattr(self.adapter, 'current_features'):
                            ema_15 = self.adapter.current_features.get(f'ema_15_{symbol.lower()}')

                        # Safety check for dist_to_ema calculations
                        dist_to_ema = 0.0
                        if price is not None and ema_15 is not None:
                            dist_to_ema = price - ema_15

                        chart_time = getattr(self.adapter, 'chart_time', None)
                        if chart_time is None and hasattr(self.adapter, 'current_features'):
                            chart_time = self.adapter.current_features.get('chart_time')
                            # SURGICAL FIX: Force extraction from Market Depth payload if adapter didn't map it
                        if chart_time is None and hasattr(self.adapter, 'get_market_depth'):
                            _md = self.adapter.get_market_depth(symbol)
                            if isinstance(_md, dict):
                                chart_time = _md.get('chart_time') or _md.get('timestamp')
                        if chart_time:
                            state.state_manager.update_market_time(chart_time)

                        current_session = logic.get_market_session()
                        
                        # 🛑 THE GATEKEEPER: Only let MES update the Floor and Ceiling
                        if symbol == 'MES':
                            logic.update_session_anchors(price, current_session)
                        
                        # 1. Distance to Floor
                        dist_to_low = "N/A"
                        if price is not None and state.state_manager.opening_range_low is not None:
                            dist_to_low = price - state.state_manager.opening_range_low
                        
                        # 2. Distance to Ceiling (Using getattr to prevent crashes if it's missing)
                        range_high = getattr(state.state_manager, 'opening_range_high', None)
                        dist_to_high = "N/A"
                        if price is not None and range_high is not None:
                            dist_to_high = range_high - price
                        
                        # 3. Print the full 360-degree view
                        log_to_both(f"HEARTBEAT: {symbol} @ {price} | 15m EMA: {ema_15} | Dist to EMA: {dist_to_ema:.2f} | Session: {current_session} | Dist to Low: {dist_to_low} | Dist to High: {dist_to_high}")
                        state.state_manager.add_price(symbol, price)
                        log_to_both(f"--- CURRENT SESSION CVD: {state.state_manager.session_cvd} ---")
                        self.price_buffer[symbol].append(price)
                        # --- GLOBAL ICEBERG RADAR ---
                        if symbol == 'MES':
                            # Ask NinjaTrader for the DOM data first!
                            market_depth = self.adapter.get_market_depth(symbol)
                            if market_depth:
                                try:
                                    bids = market_depth.get('bids', [])
                                    asks = market_depth.get('asks', [])
                                    
                                    if bids and asks:
                                        floor_price = max(bids, key=lambda x: float(x[1]))[0]
                                        floor_vol = max(bids, key=lambda x: float(x[1]))[1]
                                        
                                        ceil_price = max(asks, key=lambda x: float(x[1]))[0]
                                        ceil_vol = max(asks, key=lambda x: float(x[1]))[1]
                                        
                                        log_to_both(f"[🧊 ICEBERG RADAR] Floor: {floor_price} ({floor_vol} vol) | Ceiling: {ceil_price} ({ceil_vol} vol)")
                                except Exception as e:
                                    pass
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
                                    log_to_both(f"--- CHOP INDEX (MES): {chop_index:.2f} ---")

                                # Reset for next bar
                                self.price_buffer[symbol] = []
                                self.last_bar_time[symbol] = current_time
                                
                                if symbol == 'MES':
                                    state.state_manager.cvd_history.append(state.state_manager.session_cvd)


                        # Only perform deep analysis for the execution symbol (MES)
                        if symbol == 'MES':
                            market_depth = self.adapter.get_market_depth(symbol)
                            if market_depth is not None:
                                market_depth['ema_15'] = ema_15
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
                                log_to_both(f"--- AI RECOMMENDS: {action_map.get(ai_action, 'UNKNOWN')} ---")

                            # --- STRATEGY MANAGER ---
                            signal = None

                            thresholds = logic.get_dynamic_thresholds()
                            if isinstance(thresholds, float):
                                thresholds = {'min_confidence': thresholds, 'halt': False, 'min_atr': 2.0, 'strategy': 'ALL'}

                            if thresholds['halt']:
                                pass
                            elif in_cooldown:
                                cooldown_remaining = 300 - (state.state_manager.get_current_time().timestamp() - self.last_trade_time)
                                log_to_both(f"--- ACTIVE PROFILE: COOLDOWN (Cooling down for {int(cooldown_remaining)}s) ---")
                                continue
                            elif in_timeout:
                                log_to_both(f"--- ACTIVE PROFILE: TIME-OUT (Active for {int(state.state_manager.time_out_until - time.time())}s) ---")
                            elif chop_index > 50.0:
                                session_name = logic.get_market_session()
                                log_to_both(f"--- ACTIVE PROFILE: {session_name} (CHOP: {chop_index:.2f} - SIDEWAYS MARKET. PING-PONG AGENT ACTIVE) ---")
                                signal = logic.analyze_mean_reversion(symbol, market_depth, state.state_manager.price_history.get(symbol, []), chop_index)
                            else:
                                session_name = logic.get_market_session()
                                log_to_both(f"--- ACTIVE PROFILE: {session_name} (CHOP: {chop_index:.2f} - TRENDING. SNIPERS ACTIVE) ---")
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
                                log_to_both(f"--- SIGNAL TRACE [{symbol}] ---")

                                # 0. Core Strategy Filters (Trend & Volatility)
                                trend = signal.get('trend')
                                market_trend = trend
                                signal_direction = signal.get('signal_direction')
                                if not signal_direction:
                                    signal_direction = 'LONG' if 'BUY' in signal.get('type', '').upper() else 'SHORT'
                                
                                if market_trend in ['BULLISH', 'BEARISH']:
                                    if signal_direction == 'LONG' and market_trend == 'BULLISH':
                                        trend_pass = True
                                    elif signal_direction == 'SHORT' and market_trend == 'BEARISH':
                                        trend_pass = True
                                    else:
                                        trend_pass = False
                                    signal['trend_pass'] = trend_pass
                                else:
                                    trend_pass = signal.get('trend_pass', False)
                                    signal['trend_pass'] = trend_pass

                                vol_pass = signal.get('volatility_pass', True)
                                
                                atr = signal.get('atr')
                                if atr is None:
                                    atr = logic.get_current_atr(state.state_manager.price_history.get(symbol, []))
                                    signal['atr'] = atr
                                
                                current_atr = atr
                                session_min_atr = thresholds['min_atr']
                                if current_atr >= session_min_atr:
                                    vol_pass = True
                                else:
                                    vol_pass = False
                                signal['volatility_pass'] = vol_pass
                                
                                if not trend_pass:
                                    log_to_both(f"[CHECK] Trend Filter: [FAIL] (Market is {market_trend})")
                                else:
                                    log_to_both(f"[CHECK] Trend Filter: [PASS]")
                                    
                                if not vol_pass:
                                    log_to_both(f"[CHECK] Volatility Filter: [FAIL] (ATR {signal.get('atr', 0.0):.2f})")
                                else:
                                    log_to_both(f"[CHECK] Volatility Filter: [PASS]")
                                
                                # 1. Market Regime Check
                                log_to_both(f"[CHECK] Market Regime: [PASS] ({chop_index:.2f})")

                                # 2. ML Confidence & Dynamic Thresholds
                                ml_pass = True
                                ml_val = signal.get('ml_confidence_value')
                                ml_threshold = thresholds['min_confidence']
                                
                                if ml_val is not None:
                                    if ml_val >= ml_threshold:
                                        log_to_both(f"[CHECK] ML Confidence: [PASS] ({ml_val:.2f}% >= {ml_threshold}%)")
                                    else:
                                        log_to_both(f"[CHECK] ML Confidence: [FAIL] ({ml_val:.2f}% < {ml_threshold}%)")
                                        ml_pass = False
                                else:
                                    log_to_both(f"[CHECK] ML Confidence: [FAIL] (No ML score provided by strategy)")
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
                                    log_to_both(f"[CHECK] RL Supervisor: [{rl_status}] ({ai_action_str})")
                                else:
                                    log_to_both(f"[CHECK] RL Supervisor: [PASS] (N/A - No Model)")

                                # 4. Live Position Hard Guard (Signal Pre-check)
                                live_nt = getattr(state.state_manager, 'live_nt_positions', {})
                                current_pos = 0
                                for k, v in live_nt.items():
                                    if symbol in k:
                                        current_pos = v
                                        break
                                pos_guard_pass = True
                                
                                if signal['type'] == 'BUY_SIGNAL' and current_pos > 0:
                                    pos_guard_pass = False
                                    log_to_both(f"[CHECK] Hard Guard: [FAIL] (Already Long)")
                                elif signal['type'] == 'SELL_SIGNAL' and current_pos < 0:
                                    pos_guard_pass = False
                                    log_to_both(f"[CHECK] Hard Guard: [FAIL] (Already Short)")
                                else:
                                    log_to_both(f"[CHECK] Hard Guard: [PASS]")

                                # 5. Micro-CVD Hollow Fakeout Guard (Adaptive)
                                cvd_pass = True
                                cvd_hist = state.state_manager.cvd_history
                                
                                if len(cvd_hist) >= 5:
                                    current_cvd = state.state_manager.session_cvd
                                    micro_cvd_5m = current_cvd - cvd_hist[-5]
                                    
                                    # Calculate what a "normal" 5m volume push looks like right now
                                    cvd_efforts = [abs(cvd_hist[i] - cvd_hist[i-5]) for i in range(5, len(cvd_hist))]
                                    calculated_avg = sum(cvd_efforts) / len(cvd_efforts) if cvd_efforts else 50.0
                                    
                                    # THE FIX: Enforce a hard minimum floor so the requirement never drops to zero
                                    avg_cvd_effort = max(calculated_avg, 50.0)
                                    
                                    # Require the current setup to have at least 30% of the recent average volume
                                    required_effort = avg_cvd_effort * 0.20
                                    
                                    if signal_direction == 'LONG':
                                        if micro_cvd_5m < 0 or abs(micro_cvd_5m) < required_effort:
                                            cvd_pass = False
                                            log_to_both(f"[CHECK] Micro-CVD Guard: [FAIL] (Hollow/Counter Move: {micro_cvd_5m:.1f} vol vs Req +{required_effort:.1f})")
                                        else:
                                            log_to_both(f"[CHECK] Micro-CVD Guard: [PASS] (Solid Volume: {micro_cvd_5m:.1f} | Req: +{required_effort:.1f})")
                                    elif signal_direction == 'SHORT':
                                        if micro_cvd_5m > 0 or abs(micro_cvd_5m) < required_effort:
                                            cvd_pass = False
                                            log_to_both(f"[CHECK] Micro-CVD Guard: [FAIL] (Hollow/Counter Move: {micro_cvd_5m:.1f} vol vs Req -{required_effort:.1f})")
                                        else:
                                            log_to_both(f"[CHECK] Micro-CVD Guard: [PASS] (Solid Volume: {micro_cvd_5m:.1f} | Req: -{required_effort:.1f})")
                                else:
                                    log_to_both(f"[CHECK] Micro-CVD Guard: [PASS] (Warming up volume memory...)")

                                # FINAL DECISION
                                if not (trend_pass and vol_pass and ml_pass and rl_pass and pos_guard_pass and cvd_pass):
                                    log_to_both("--- FINAL DECISION: [VETOED] ---")
                                    if not state.state_manager.dev_mode:
                                        continue
                                
                                log_to_both("--- FINAL DECISION: [EXECUTED] ---")
                                pending_signals = state.state_manager.get_pending_signals()
                                is_duplicate = any(s['price'] == signal['price'] and s['type'] == signal['type'] for s in pending_signals)
                                
                                if not is_duplicate:
                                    state.state_manager.add_pending_signal(signal)
                                    try:
                                        if 'context_data' in signal:
                                            logger.log_signal(signal, signal['context_data'], 'PENDING')
                                    except Exception as e:
                                        print(f"Logger warning: {e}")
                                    reason = signal.get('reason', 'Unknown')
                                    confidence_score_str = signal.get('ml_confidence', f"{signal.get('confidence_score', 0):.2f}%" if 'confidence_score' in signal else 'N/A (DEV)')
                                    log_to_both(f"!!! NEW SIGNAL [{reason}]: {signal['type']} at {signal['price']} for {signal['size']} with {confidence_score_str} confidence!!!")

                                    # --- 🚀 AUTO-TRADE AUTOPILOT ---
                                    if state.state_manager.auto_buy_enabled and signal['type'] in ['BUY_SIGNAL', 'SELL_SIGNAL']:
                                        current_time = time.time()
                                        # 🛑 SURGICAL FIX: Anti-Machine Gun Lock
                                        if (abs(current_pos) > 0 or len(state.state_manager.get_active_positions()) > 0) and not getattr(state.state_manager, 'is_reversing', False):
                                            continue
                                        if current_time - state.state_manager.last_trade_time > 5:
                                            state.state_manager.last_trade_time = current_time
                                            if current_time - signal['timestamp'] <= 2:
                                                log_to_both(f"🚀 AUTO-TRADE TRIGGERED: {signal['type']}")
                                                
                                                if not getattr(self, '_is_executing', False):
                                                    try:
                                                        self._is_executing = True
                                                        exec_price = signal.get('price', price)
                                                        dynamic_size = logic.calculate_position_size(exec_price, state.state_manager.price_history)
                                                        
                                                        trade_executed = False
                                                        pos_type = 'BUY'
                                                        
                                                        if signal['type'] == 'BUY_SIGNAL':
                                                            if current_pos < 0:
                                                                if not getattr(state.state_manager, 'is_reversing', False):
                                                                    log_to_both(f"--- REVERSAL: Flattening Short {abs(current_pos)} before Auto-Buy ---")
                                                                    state.state_manager.is_reversing = True
                                                                    state.state_manager.reversal_start_time = time.time()
                                                                    self.adapter.execute_buy(symbol, abs(current_pos), exec_price, signal_id='REVERSAL')
                                                                continue
                                                            trade_executed = self.adapter.execute_buy(symbol, dynamic_size, exec_price, signal_id=str(signal.get('id')))
                                                        else:
                                                            pos_type = 'SELL'
                                                            if current_pos > 0:
                                                                if not getattr(state.state_manager, 'is_reversing', False):
                                                                    log_to_both(f"--- REVERSAL: Flattening Long {current_pos} before Auto-Sell ---")
                                                                    state.state_manager.is_reversing = True
                                                                    state.state_manager.reversal_start_time = time.time()
                                                                    self.adapter.execute_sell(symbol, current_pos, exec_price, signal_id='REVERSAL')
                                                                continue
                                                            # Check for the AI sniper's direction, default to SELL for regular signals
                                                            side_to_send = 'SELL' # Default for regular signals
                                                            if signal.get('signal_direction') == 'SHORT':
                                                                side_to_send = 'SHORT' # Override for AI Short signal
                                                                pos_type = 'SHORT'
                                                            trade_executed = self.adapter.execute_sell(symbol, dynamic_size, exec_price, signal_id=str(signal.get('id')), side=side_to_send)
                                                        
                                                        if trade_executed:
                                                            # --- REPLAY BYPASS: Force Broker Memory Update ---
                                                            # Since NT8 drops entry receipts in replay mode, forcefully assume it filled immediately.
                                                            if not hasattr(state.state_manager, 'live_nt_positions'):
                                                                state.state_manager.live_nt_positions = {}
                                                            current_qty = state.state_manager.live_nt_positions.get(symbol, 0)
                                                            if pos_type == 'SHORT':
                                                                state.state_manager.live_nt_positions[symbol] = current_qty - dynamic_size
                                                            else:
                                                                state.state_manager.live_nt_positions[symbol] = current_qty + dynamic_size
                                                            position = {
                                                                'symbol': symbol,
                                                                'entry_price': exec_price,
                                                                'size': dynamic_size,
                                                                'type': pos_type,
                                                                'timestamp': state.state_manager.get_current_time().timestamp(),
                                                                'real_timestamp': time.time(),
                                                                'signal_timestamp': float(signal.get('timestamp', state.state_manager.get_current_time().timestamp())),
                                                                'signal_id': signal.get('id', '')
                                                            }
                                                            
                                                            # Deduplication Logic
                                                            existing_positions = state.state_manager.get_active_positions()
                                                            if any(str(p.get('signal_timestamp')) == str(position['signal_timestamp']) for p in existing_positions):
                                                                log_to_both(f"[🛡️ DE-DUP] Blocking ghost position for signal {position['signal_timestamp']}.")
                                                            else:
                                                                state.state_manager.add_position(position)
                                                                try:
                                                                    logger.update_user_decision(str(signal['timestamp']), 'APPROVED')
                                                                    state.state_manager.set_signal_approved()
                                                                except Exception as e:
                                                                    print(f"Logger warning: {e}")
                                                                
                                                                # --- ENTRY TRIGGER: Start Log Capture ---
                                                                sig_id_str = str(position['signal_timestamp'])
                                                                state.state_manager.active_trade_logs[sig_id_str] = list(state.state_manager.log_rolling_buffer)[-200:]
                                                                log_to_both(f"--- LOG CAPTURE STARTED FOR SIGNAL {sig_id_str} ---")
                                                            log_to_both(f"✅ AUTO-TRADE EXECUTED: {symbol} at {exec_price} ({pos_type})")
                                                    finally:
                                                        self._is_executing = False
                                            
                                            state.state_manager.remove_pending_signal(signal)

                except Exception as e:
                    print(f"Error in engine loop: {e}")
            
            print(f'Loop latency: {time.time() - start_time:.4f}s')
            time.sleep(0.05) #0.5 or 1. remember this
        
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
        state.state_manager.reset_cvd()
        print("--- Session CVD Reset to 0.0 ---")
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
