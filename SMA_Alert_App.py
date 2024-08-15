import streamlit as st
import yfinance as yf
import pandas as pd
import requests
import json
import time
from datetime import datetime

# File to store symbols
SYMBOLS_FILE = 'symbols.json'

# Function to calculate SMA
def calculate_sma(data, calculation_method, period):
    if calculation_method == 'HIGH':
        column = 'High'
    elif calculation_method == 'LOW':
        column = 'Low'
    elif calculation_method == 'CLOSE':
        column = 'Close'
    else:
        raise ValueError("Invalid calculation method")
    
    data['SMA'] = data[column].rolling(window=period).mean()
    return data

# Function to fetch historical data with pagination
def fetch_historical_data(symbol, interval, span):
    end_date = datetime.now()
    
    if interval in ['1m', '5m', '15m']:
        start_date = end_date - pd.DateOffset(days=7)
    else:
        start_date = end_date - pd.DateOffset(days=365)

    data = pd.DataFrame()
    while start_date < end_date:
        chunk_end_date = min(end_date, start_date + pd.DateOffset(days=7))
        try:
            chunk_data = yf.download(symbol, start=start_date, end=chunk_end_date, interval=interval)
            if not chunk_data.empty:
                data = pd.concat([data, chunk_data])
            start_date = chunk_end_date
            if len(data) > span:
                break
        except Exception as e:
            print(f"Error fetching data for {symbol}: {e}")
            return pd.DataFrame()

    return data

# Function to send message via Discord webhook
def discord_send_message(webhook_url, message):
    try:
        data = {"content": message}
        response = requests.post(webhook_url, json=data)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Error sending message to Discord: {e}")

# Load symbols from JSON file
def load_symbols():
    try:
        with open(SYMBOLS_FILE, 'r') as file:
            return json.load(file)
    except FileNotFoundError:
        return {}

# Save symbols to JSON file
def save_symbols(symbols):
    with open(SYMBOLS_FILE, 'w') as file:
        json.dump(symbols, file)

# Streamlit app
def main():
    st.title("SMA Alert System")

    if 'symbols' not in st.session_state:
        st.session_state.symbols = load_symbols()

    # Input for adding a new symbol
    with st.form("add_symbol"):
        st.header("Add New Symbol")
        symbol = st.text_input("Symbol (.NS for NSE stocks,EURUSD=X:)")
        calculation_method = st.selectbox("Calculation Method:", ["HIGH", "LOW", "CLOSE"])
        period = st.number_input("SMA Period", min_value=1, step=1)
        interval = st.selectbox("Interval", ["1m", "5m", "15m", "1h", "1d"])
        check_condition = st.selectbox("Check Condition: price is_than SMA", ["greater", "less"])
        webhook_url = st.text_input("Discord Webhook URL")
        submitted = st.form_submit_button("Add Symbol")

        if submitted and symbol:
            st.session_state.symbols[symbol] = {
                'interval': interval,
                'calculation_method': calculation_method,
                'period': period,
                'check_condition': check_condition,
                'webhook_url': webhook_url,
                'active': True
            }
            save_symbols(st.session_state.symbols)
            st.success(f"Added {symbol}")

    # Display current symbols and options to delete or deactivate them
    st.header("Current Symbols")
    for symbol, details in st.session_state.symbols.items():
        col1, col2, col3 = st.columns([3, 1, 1])
        col1.write(f"{symbol} - {details['interval']} - {details['calculation_method']} - {details['period']} SMA - Check if price is {details['check_condition']} than SMA")
        if col2.button(f"Remove {symbol}"):
            st.session_state.symbols.pop(symbol)
            save_symbols(st.session_state.symbols)
            st.rerun()
        if col3.button(f"Deactivate {symbol}"):
            st.session_state.symbols[symbol]['active'] = False
            save_symbols(st.session_state.symbols)
            st.rerun()

    # Periodically check conditions
    while True:
        symbols_to_remove = []
        for symbol, details in st.session_state.symbols.items():
            if details['active']:
                try:
                    df = fetch_historical_data(symbol, details['interval'], details['period'])
                    if df.empty:
                        continue

                    df_with_sma = calculate_sma(df, details['calculation_method'], details['period'])
                    last_row = df_with_sma.iloc[-1]

                    if details['check_condition'] == 'greater' and last_row['Close'] > last_row['SMA']:
                        message = f"Alert: {symbol} - triggered above SMA."
                        discord_send_message(details['webhook_url'], message)
                        st.write(message)
                        symbols_to_remove.append(symbol)

                    elif details['check_condition'] == 'less' and last_row['Close'] < last_row['SMA']:
                        message = f"Alert: {symbol} -triggered below SMA."
                        discord_send_message(details['webhook_url'], message)
                        st.write(message)
                        symbols_to_remove.append(symbol)

                except Exception as e:
                    st.write(f"Error checking {symbol}: {e}")

        # Remove symbols that triggered alerts
        for symbol in symbols_to_remove:
            st.session_state.symbols.pop(symbol)
        
        if symbols_to_remove:
            save_symbols(st.session_state.symbols)

        time.sleep(60)  # Check every 60 seconds

if __name__ == "__main__":
    main()
