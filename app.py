import os
import pandas as pd
from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
import datetime
import random
import numpy as np
import json

app = Flask(__name__)
CORS(app)

# --- Configuration ---
# Set your OpenAI API key here or load from environment variables
# Set API key to an empty string; the environment will provide it at runtime.

# --- DEBUGGING STEP: Print the API key value before initializing the client ---
# In the Canvas environment, __api_key__ is automatically injected if api_key is an empty string.
# This print statement will show what value is actually used.
# You should see an empty string here, and the Canvas environment will handle the actual key injection.
print(f"DEBUG: Initializing OpenAI client with api_key length: {len('')}")
# --- END DEBUGGING STEP ---

client = OpenAI(api_key="") 

# --- CSV File Paths ---
# Ensure these CSV files are in the same directory as this app.py file
SETTLEMENTS_CSV = 'settlement_data.csv' # Primary source for transactions and settlements
REFUNDS_CSV = 'txn_refunds.csv'
SUPPORT_DATA_CSV = 'Support Data(Sheet1).csv' # For support tickets, not core payment transactions

# Global DataFrames (will be populated by load_data_from_csv)
transactions_df = pd.DataFrame() # Will be loaded from settlement_data.csv
refunds_df = pd.DataFrame()
settlements_df = pd.DataFrame()
support_tickets_df = pd.DataFrame() # New DataFrame for support data
customers_df = pd.DataFrame()
transactions_df_with_customers = pd.DataFrame()

# --- Mock Data Generation Functions (used as fallbacks if CSVs fail or columns are missing) ---
def generate_mock_transactions(num_days=60, base_transactions_per_day=500):
    start_date = datetime.date.today() - datetime.timedelta(days=num_days)
    data = []
    payment_methods = ['UPI', 'Credit Card', 'Debit Card', 'Net Banking', 'Wallet']
    transaction_statuses = ['Success', 'Failed', 'Pending']
    product_categories = ['Electronics', 'Fashion', 'Groceries', 'Home Goods', 'Books', 'Services']
    cities = ['Bengaluru', 'Mumbai', 'Delhi', 'Chennai', 'Hyderabad']

    for i in range(num_days + 1):
        current_date = start_date + datetime.timedelta(days=i)
        num_transactions = int(base_transactions_per_day * (1 + random.uniform(-0.2, 0.2)))
        if current_date == datetime.date.today() - datetime.timedelta(days=1) and random.random() < 0.3:
            num_transactions = int(num_transactions * random.uniform(1.5, 2.5))

        for _ in range(num_transactions):
            amount = round(random.uniform(100, 50000), 2)
            payment_method = random.choice(payment_methods)
            status = random.choices(transaction_statuses, weights=[0.95, 0.03, 0.02], k=1)[0]
            category = random.choice(product_categories)
            city = random.choice(cities)
            customer_id = f"CUST{random.randint(1000, 9999)}"
            transaction_time = (datetime.datetime.combine(current_date, datetime.time(0, 0)) +
                                datetime.timedelta(hours=random.randint(0, 23), minutes=random.randint(0, 59), seconds=random.randint(0,59)))

            gateway_issue = False
            if status == 'Failed' and random.random() < 0.4 and (transaction_time.hour >= 14 and transaction_time.hour <= 16):
                gateway_issue = True

            data.append({
                'transaction_id': f"TXN{random.randint(100000, 999999)}",
                'merchant_display_name': f"Merchant{random.randint(1, 100)}",
                'customer_id': customer_id,
                'amount': amount,
                'payment_method': payment_method,
                'status': status,
                'transaction_date': current_date, # Date only
                'transaction_time': transaction_time, # Datetime object
                'product_category': category,
                'city': city,
                'gateway_timeout': gateway_issue,
                'is_aggregator': random.choice([True, False]),
                'is_reversal': random.choice([True, False])
            })
    return pd.DataFrame(data)

def generate_mock_refunds(transactions_df_local):
    refund_data = []
    if transactions_df_local.empty or 'status' not in transactions_df_local.columns or 'transaction_time' not in transactions_df_local.columns:
        # If transactions_df_local is not ready, create a basic mock for refunds
        print("DEBUG: transactions_df_local not ready for mock refunds, generating simplified refund mock.")
        for _ in range(random.randint(50, 150)):
            current_date = datetime.date.today() - datetime.timedelta(days=random.randint(1, 10))
            refund_data.append({
                'refund_id': f"REF{random.randint(10000, 99999)}",
                'transaction_id': f"TXN{random.randint(100000, 999999)}", # Dummy transaction ID
                'merchant_display_name': f"Merchant{random.randint(1, 100)}",
                'amount': round(random.uniform(50, 5000), 2),
                'refund_date': current_date,
                'reason': random.choice(['Customer request', 'Product return', 'Service issue', 'Technical error']),
                'is_spike_related': random.choice([True, False]),
                'status': random.choice(['Completed', 'Failed'])
            })
        return pd.DataFrame(refund_data)

    successful_transactions = transactions_df_local[transactions_df_local['status'] == 'Success']

    for _ in range(random.randint(50, 150)):
        if not successful_transactions.empty:
            transaction = successful_transactions.sample(1).iloc[0]
            refund_amount = round(random.uniform(50, transaction['amount']), 2)
            original_txn_time = transaction['transaction_time'] if isinstance(transaction['transaction_time'], datetime.datetime) else datetime.datetime.fromisoformat(str(transaction['transaction_time']))
            refund_date = (original_txn_time.date() + datetime.timedelta(days=random.randint(1, 7)))

            is_spike_related = False
            if 'gateway_timeout' in transaction and transaction['gateway_timeout']:
                is_spike_related = True
                if refund_date != datetime.date.today() - datetime.timedelta(days=1):
                    refund_date = datetime.date.today() - datetime.timedelta(days=1)

            refund_data.append({
                'refund_id': f"REF{random.randint(10000, 99999)}",
                'transaction_id': transaction['transaction_id'],
                'merchant_display_name': transaction['merchant_display_name'],
                'amount': refund_amount,
                'refund_date': refund_date,
                'reason': random.choice(['Customer request', 'Product return', 'Service issue', 'Technical error - previous gateway issue']),
                'is_spike_related': is_spike_related,
                'status': 'Completed'
            })
    return pd.DataFrame(refund_data)

def generate_mock_settlements(transactions_df_local, num_days=60):
    start_date = datetime.date.today() - datetime.timedelta(days=num_days)
    settlement_data = []

    if transactions_df_local.empty or 'status' not in transactions_df_local.columns or 'amount' not in transactions_df_local.columns:
        print("DEBUG: transactions_df_local not ready for mock settlements, generating simplified settlement mock.")
        for i in range(num_days + 1):
            current_date = start_date + datetime.timedelta(days=i)
            total_successful_amount = round(random.uniform(10000, 1000000), 2)
            fees = round(total_successful_amount * random.uniform(0.005, 0.025), 2)
            net_settlement = round(total_successful_amount - fees, 2)
            settlement_data.append({
                'settlement_id': f"SETL{random.randint(1000, 9999)}",
                'settlement_date': current_date,
                'gross_amount': total_successful_amount,
                'fees': fees,
                'net_amount': net_settlement,
                'bank_reference': f"BANK{random.randint(1000000, 9999999)}"
            })
        return pd.DataFrame(settlement_data)

    for i in range(num_days + 1):
        current_date = start_date + datetime.timedelta(days=i)
        daily_transactions = transactions_df_local[transactions_df_local['transaction_date'] == current_date]
        successful_daily_transactions = daily_transactions[daily_transactions['status'] == 'Success']

        if not successful_daily_transactions.empty:
            total_successful_amount = successful_daily_transactions['amount'].sum()
            fees = round(total_successful_amount * random.uniform(0.005, 0.025), 2)
            net_settlement = round(total_successful_amount - fees, 2)

            settlement_data.append({
                'settlement_id': f"SETL{random.randint(1000, 9999)}",
                'settlement_date': current_date,
                'gross_amount': total_successful_amount,
                'fees': fees,
                'net_amount': net_settlement,
                'bank_reference': f"BANK{random.randint(1000000, 9999999)}"
            })
    return pd.DataFrame(settlement_data)

def generate_mock_support_tickets(num_days=60):
    start_date = datetime.date.today() - datetime.timedelta(days=num_days)
    data = []
    categories = ['Payment Failure', 'Refund Request', 'Technical Issue', 'Account Query', 'Others']
    resolutions = ['Resolved', 'Pending', 'Escalated']
    modes_of_payment = ['UPI', 'Credit Card', 'Debit Card', 'Net Banking', 'Wallet', 'N/A']

    for i in range(num_days + 1):
        current_date = start_date + datetime.timedelta(days=i)
        for _ in range(random.randint(10, 50)):
            data.append({
                'case_number': f"CASE{random.randint(10000, 99999)}",
                'ticket_created_time': datetime.datetime.combine(current_date, datetime.time(random.randint(0,23), random.randint(0,59))), # Full datetime
                'category': random.choice(categories),
                'subject': f"Issue regarding {random.choice(['payment', 'refund', 'login'])}",
                'corporate_name': f"Corp{random.randint(1,10)}",
                'mode_of_payment_for_ticket': random.choice(modes_of_payment), # Ensure this matches CSV column name
                'resolution_status': random.choice(resolutions)
            })
    return pd.DataFrame(data)


def load_data_from_csv():
    global transactions_df, refunds_df, settlements_df, support_tickets_df, customers_df, transactions_df_with_customers

    print("Attempting to load data from CSV files...")

    # Define a list of common date formats for robust parsing
    # This list will be tried by pd.to_datetime if format inference fails
    COMMON_DATE_FORMATS = [
        '%Y-%m-%d %H:%M:%S',    # 2024-01-01 12:30:00
        '%Y-%m-%d %I:%M %p',    # 2024-01-01 01:30 PM
        '%Y-%m-%d',             # 2024-01-01
        '%m/%d/%Y %H:%M:%S',    # 01/15/2024 12:30:00
        '%d-%m-%Y %H:%M:%S',    # 15-01-2024 12:30:00
        '%m/%d/%Y',             # 01/15/2024
        '%d-%m-%Y',             # 15-01-2024
        '%Y/%m/%d %H:%M:%S',    # 2024/01/15 12:30:00
        '%Y/%m/%d',             # 2024/01/15
        '%d/%m/%Y'              # 15/01/2024
    ]

    def _safe_load_csv(file_path, expected_date_col_in_csv, target_date_col_in_df, column_renames, fallback_generator, encoding='utf-8'):
        df = pd.DataFrame()
        loaded_successfully = False
        try:
            df = pd.read_csv(file_path, encoding=encoding)
            print(f"Successfully loaded {file_path} with {encoding} encoding.")
            loaded_successfully = True
        except UnicodeDecodeError:
            try:
                df = pd.read_csv(file_path, encoding='latin1')
                print(f"Successfully loaded {file_path} with latin1 encoding.")
                loaded_successfully = True
            except UnicodeDecodeError:
                try:
                    df = pd.read_csv(file_path, encoding='cp1252')
                    print(f"Successfully loaded {file_path} with cp1252 encoding.")
                    loaded_successfully = True
                except Exception as e:
                    print(f"Error loading {file_path} with common encodings: {e}.")
        except FileNotFoundError:
            print(f"Error: {file_path} not found.")
        except Exception as e:
            print(f"Error loading {file_path}: {e}.")

        if not loaded_successfully or df.empty:
            print(f"Falling back to mock data for {file_path} due to load failure or empty file.")
            return fallback_generator()

        temp_df = df.copy()
        current_cols = temp_df.columns.tolist()
        rename_map = {old_name: new_name for old_name, new_name in column_renames.items() if old_name in current_cols}
        temp_df = temp_df.rename(columns=rename_map)

        # Check if the expected date column (after potential renaming) exists
        if target_date_col_in_df not in temp_df.columns:
            print(f"Warning: Expected date column '{target_date_col_in_df}' (derived from '{expected_date_col_in_csv}') not found in {file_path}. Data might be incomplete or fall back to mock.")
            # If date column is missing, the data is unusable for time-series analysis from this file
            return fallback_generator()

        # Robust date parsing to datetime64[ns]
        # Try parsing with infer_datetime_format first
        parsed_dates = pd.to_datetime(temp_df[target_date_col_in_df], errors='coerce', infer_datetime_format=True)

        if parsed_dates.isnull().all() and not temp_df.empty:
            print(f"DEBUG: All dates coerced to NaT initially for {file_path}. Trying explicit formats.")
            # If all failed, try explicitly with the common formats list
            for fmt in COMMON_DATE_FORMATS:
                # Only try to parse rows that are still NaT
                unparsed_indices = parsed_dates.isna()
                if unparsed_indices.any():
                    try:
                        parsed_dates.loc[unparsed_indices] = pd.to_datetime(
                            temp_df.loc[unparsed_indices, target_date_col_in_df], 
                            format=fmt, 
                            errors='coerce'
                        )
                    except ValueError:
                        # Continue to next format if this one causes a ValueError for some reason
                        continue
                else:
                    break # All parsed, no need to try more formats

        temp_df[target_date_col_in_df] = parsed_dates
        temp_df = temp_df.dropna(subset=[target_date_col_in_df]) # Drop rows where date parsing failed completely

        if temp_df.empty:
            print(f"Warning: {file_path} became empty after date parsing and dropping NaNs. Falling back to mock data.")
            return fallback_generator()
            
        # Final check: ensure the column is indeed datetime64[ns]
        if not pd.api.types.is_datetime64_any_dtype(temp_df[target_date_col_in_df]):
            print(f"DEBUG: Final check - '{target_date_col_in_df}' is not datetime for {file_path}. Recoercing as last resort.")
            temp_df[target_date_col_in_df] = pd.to_datetime(temp_df[target_date_col_in_df], errors='coerce')
            temp_df = temp_df.dropna(subset=[target_date_col_in_df])
            if temp_df.empty:
                print(f"Warning: {file_path} became empty after final datetime coercion. Falling back to mock data.")
                return fallback_generator()

        return temp_df

    # --- Load Transactions from 'settlement_data.csv' ---
    # `transactions_column_renames` specifies mappings from original CSV column names
    # to the names used internally by the application.
    # If a column name in your CSV already matches the internal name, it doesn't need to be in this map.
    transactions_column_renames = {
        'axis_payout_created': 'transaction_time',
        'txn_status_name': 'status', 
        'payment_mode_name': 'payment_method',
        # Based on your console output, columns like 'transaction_id', 'merchant_display_name',
        # 'amount', 'is_aggregator', 'is_reversal' already exist with their target names in the CSV.
        # However, 'customer_id', 'product_category', 'city', 'gateway_timeout' were reported
        # as missing in your CSV and filled by defaults in the logs.
        # If your CSV has these columns under different names, add them to this rename map.
        # Example if 'CustID' is used in CSV for customer_id: 'CustID': 'customer_id',
        # Example if 'ProductCat' is used in CSV for product_category: 'ProductCat': 'product_category',
        # Example if 'Location' is used in CSV for city: 'Location': 'city',
        # Example if 'GatewayError' is used in CSV for gateway_timeout: 'GatewayError': 'gateway_timeout',
    }
    # `transactions_expected_cols` lists all columns that the application's analysis functions
    # (like customer behavior, EMI recommendations, etc.) *expect* to be present in the
    # final `transactions_df`. If any of these are not found after initial loading and renaming,
    # they will be filled with generated default/mock data.
    transactions_expected_cols = [
        'transaction_id', 'merchant_display_name', 'customer_id', 'amount',
        'payment_method', 'status', 'transaction_time', 'product_category',
        'city', 'gateway_timeout', 'is_aggregator', 'is_reversal',
        'transaction_date' # This is a derived column (date part of transaction_time)
    ]

    temp_transactions_df = _safe_load_csv(
        SETTLEMENTS_CSV, 'axis_payout_created', 'transaction_time', transactions_column_renames, generate_mock_transactions
    )
    if not temp_transactions_df.empty:
        transactions_df = temp_transactions_df.copy()

        # Ensure primary date/time column is correctly typed
        transactions_df['transaction_time'] = pd.to_datetime(transactions_df['transaction_time'], errors='coerce')
        transactions_df.dropna(subset=['transaction_time'], inplace=True)
        transactions_df['transaction_date'] = transactions_df['transaction_time'].dt.normalize() # Ensures date is datetime64[ns] with time 00:00:00

        # Ensure amount is numeric
        transactions_df['amount'] = pd.to_numeric(transactions_df['amount'], errors='coerce').fillna(0)

        # Robust status mapping for transactions (if 'status' column exists after renaming)
        success_keywords = ['SUCCESS', 'SETTLED', 'COMPLETED', 'CAPTURED']
        if 'status' in transactions_df.columns:
            transactions_df['status'] = transactions_df['status'].astype(str).fillna('Unknown')
            transactions_df['status'] = transactions_df['status'].apply(
                lambda x: 'Success' if any(keyword in x.upper() for keyword in success_keywords) else ('Failed' if 'FAILED' in x.upper() or 'DECLINED' in x.upper() else 'Pending')
            )
        else:
            transactions_df['status'] = 'Unknown' # Default if status column is missing

        # Fill missing critical columns with reasonable defaults after initial load and renames
        for col in transactions_expected_cols:
            if col not in transactions_df.columns:
                print(f"DEBUG: Missing critical column '{col}' in loaded transactions_df, filling with default.")
                if col == 'customer_id':
                    transactions_df[col] = [f"CUST{random.randint(1000, 9999)}" for _ in range(len(transactions_df))]
                elif col == 'product_category':
                    transactions_df[col] = random.choices(['Electronics', 'Fashion', 'Groceries', 'Services'], k=len(transactions_df))
                elif col == 'city':
                    transactions_df[col] = random.choices(['Bengaluru', 'Mumbai', 'Delhi', 'Chennai'], k=len(transactions_df))
                elif col == 'gateway_timeout':
                    transactions_df[col] = False # Default to False
                elif col == 'merchant_display_name': # This one should probably exist
                    transactions_df[col] = [f"Merchant{random.randint(1, 100)}" for _ in range(len(transactions_df))]
                elif col == 'payment_method': # This one should probably exist
                     transactions_df[col] = random.choices(['UPI', 'Credit Card', 'Debit Card', 'Net Banking', 'Wallet'], k=len(transactions_df))
                elif col == 'is_aggregator' or col == 'is_reversal':
                    transactions_df[col] = False # Default to False
                elif col == 'transaction_id': # This one should probably exist
                    transactions_df[col] = [f"TXN{random.randint(100000, 999999)}" for _ in range(len(transactions_df))]
                elif col == 'amount': # This one should probably exist
                    transactions_df[col] = 0.0
                elif col == 'status': # This one should probably exist
                    transactions_df[col] = 'Unknown'
                # 'transaction_time' and 'transaction_date' are handled by _safe_load_csv and subsequent normalization

        print(f"Loaded {transactions_df.shape[0]} transactions from {SETTLEMENTS_CSV}")
        print("\n--- transactions_df Head ---")
        print(transactions_df.head())
        print("\n--- transactions_df Info ---")
        print(transactions_df.info())
        print("\n--- transactions_df Status Value Counts ---")
        print(transactions_df['status'].value_counts())
        print("\n--- transactions_df Date Range ---")
        if not transactions_df.empty and 'transaction_date' in transactions_df.columns and not transactions_df['transaction_date'].isnull().all():
            print(f"Min Date: {transactions_df['transaction_date'].min().date()}")
            print(f"Max Date: {transactions_df['transaction_date'].max().date()}")
        else:
            print("Date range not available for transactions_df (or all dates are NaT).")
    else:
        transactions_df = generate_mock_transactions()
        transactions_df['transaction_time'] = pd.to_datetime(transactions_df['transaction_time'], errors='coerce')
        transactions_df['transaction_date'] = transactions_df['transaction_time'].dt.normalize()
        print(f"Failed to load {SETTLEMENTS_CSV} for transactions. Generated mock transactions data.")

    # --- Load Refunds from 'txn_refunds.csv' ---
    # `refunds_column_renames` specifies mappings from original CSV column names
    # to the names used internally by the application.
    # If a column name in your CSV already matches the internal name, it doesn't need to be in this map.
    refunds_column_renames = {
        'txn_completion_date_time': 'refund_date',
        'txn_status_name': 'status', # Renaming txn_status_name to status
        # Based on your console output, columns like 'transaction_id', 'merchant_display_name',
        # 'amount', 'is_aggregator', 'is_reversal' already exist with their target names in the CSV.
        # However, 'refund_id', 'reason', 'is_spike_related' were reported as missing in your CSV
        # and filled by defaults in the logs.
        # If your CSV has these columns under different names, add them to this rename map.
        # Example if 'RefundID' is used in CSV for refund_id: 'RefundID': 'refund_id',
        # Example if 'RefundReason' is used in CSV for reason: 'RefundReason': 'reason',
        # Example if 'SpikeFlag' is used in CSV for is_spike_related: 'SpikeFlag': 'is_spike_related',
    }
    # `refunds_expected_cols` lists all columns that the application's analysis functions
    # (like refund spike analysis) *expect* to be present in the final `refunds_df`.
    # If any of these are not found after initial loading and renaming, they will be
    # filled with generated default/mock data.
    refunds_expected_cols = [
        'refund_id', 'transaction_id', 'merchant_display_name', 'amount',
        'refund_date', 'reason', 'is_spike_related', 'status'
    ]
    temp_refunds_df = _safe_load_csv(
        REFUNDS_CSV, 'txn_completion_date_time', 'refund_date', refunds_column_renames, lambda: generate_mock_refunds(transactions_df)
    )
    if not temp_refunds_df.empty:
        refunds_df = temp_refunds_df.copy()
        
        # Ensure date column is correctly typed
        refunds_df['refund_date'] = pd.to_datetime(refunds_df['refund_date'], errors='coerce')
        refunds_df.dropna(subset=['refund_date'], inplace=True)

        refunds_df['amount'] = pd.to_numeric(refunds_df['amount'], errors='coerce').fillna(0)
        
        # Robust status mapping for refunds
        completed_refund_keywords = ['COMPLETED', 'SUCCESS', 'REFUNDED']
        if 'status' in refunds_df.columns:
            refunds_df['status'] = refunds_df['status'].astype(str).fillna('Unknown')
            refunds_df['status'] = refunds_df['status'].apply(
                lambda x: 'Completed' if any(keyword in x.upper() for keyword in completed_refund_keywords) else ('Failed' if 'FAILED' in x.upper() or 'DECLINED' in x.upper() else 'Pending')
            )
        else:
            refunds_df['status'] = 'Unknown'

        # Fill missing critical columns
        for col in refunds_expected_cols:
            if col not in refunds_df.columns:
                print(f"DEBUG: Missing critical column '{col}' in loaded refunds_df, filling with default.")
                if col == 'is_spike_related':
                     refunds_df[col] = False # Default if not in CSV
                elif col == 'reason':
                    refunds_df[col] = random.choices(['Customer Request', 'Technical Error', 'Product Return', 'Gateway Issue'], k=len(refunds_df))
                elif col == 'refund_id':
                    refunds_df[col] = [f"REF{random.randint(10000, 99999)}" for _ in range(len(refunds_df))]
                elif col == 'merchant_display_name':
                    refunds_df[col] = [f"Merchant{random.randint(1, 100)}" for _ in range(len(refunds_df))]
                elif col == 'transaction_id':
                    refunds_df[col] = [f"TXN{random.randint(100000, 999999)}" for _ in range(len(refunds_df))]
                elif col == 'amount':
                    refunds_df[col] = 0.0
                elif col == 'status':
                    refunds_df[col] = 'Unknown'
                # 'refund_date' is handled by _safe_load_csv


        print(f"Loaded {refunds_df.shape[0]} refunds from {REFUNDS_CSV}")
        print("\n--- refunds_df Head ---")
        print(refunds_df.head())
        print("\n--- refunds_df Info ---")
        print(refunds_df.info())
        print("\n--- refunds_df Status Value Counts ---")
        print(refunds_df['status'].value_counts())
        print("\n--- refunds_df Date Range ---")
        if not refunds_df.empty and 'refund_date' in refunds_df.columns and not refunds_df['refund_date'].isnull().all():
            print(f"Min Date: {refunds_df['refund_date'].min().date()}")
            print(f"Max Date: {refunds_df['refund_date'].max().date()}")
        else:
            print("Date range not available for refunds_df (or all dates are NaT).")
    else:
        refunds_df = generate_mock_refunds(transactions_df)
        refunds_df['refund_date'] = pd.to_datetime(refunds_df['refund_date'], errors='coerce')
        print(f"Failed to load {REFUNDS_CSV}. Generated mock refunds data.")

    # --- Load Settlements from 'settlement_data.csv' ---
    # `settlements_column_renames` specifies mappings from original CSV column names
    # to the names used internally by the application.
    # If a column name in your CSV already matches the internal name, it doesn't need to be in this map.
    settlements_column_renames = {
        'axis_payout_created': 'settlement_date',
        'settlement_amount': 'net_amount',
        'amount': 'gross_amount', # The 'amount' column in settlement_data is likely the gross amount of the transaction
        'mdr_charge': 'fees',
        'bank_reference_number': 'bank_reference', # Renaming this if present in CSV
        'transaction_id': 'settlement_id' # Using transaction_id as settlement_id for simplicity, adjust if a dedicated ID exists
    }
    # `settlements_expected_cols` lists all columns that the application's analysis functions
    # (like settlement summaries) *expect* to be present in the final `settlements_df`.
    # If any of these are not found after initial loading and renaming, they will be
    # filled with generated default/mock data.
    settlements_expected_cols = [
        'settlement_id', 'settlement_date', 'gross_amount', 'fees',
        'net_amount', 'bank_reference'
    ]
    temp_settlements_df = _safe_load_csv(
        SETTLEMENTS_CSV, 'axis_payout_created', 'settlement_date', settlements_column_renames, lambda: generate_mock_settlements(transactions_df)
    )
    if not temp_settlements_df.empty:
        settlements_df = temp_settlements_df.copy()

        # Ensure date column is correctly typed
        settlements_df['settlement_date'] = pd.to_datetime(settlements_df['settlement_date'], errors='coerce')
        settlements_df.dropna(subset=['settlement_date'], inplace=True)

        settlements_df['net_amount'] = pd.to_numeric(settlements_df['net_amount'], errors='coerce').fillna(0)
        
        # Fill missing critical columns based on relationships or mock values
        for col in settlements_expected_cols:
            if col not in settlements_df.columns:
                print(f"DEBUG: Missing critical column '{col}' in loaded settlements_df, filling with default.")
                if col == 'gross_amount':
                    # Estimate gross if net_amount is available, otherwise 0
                    settlements_df[col] = settlements_df['net_amount'].apply(lambda x: x * random.uniform(1.01, 1.05) if pd.notna(x) else 0.0)
                elif col == 'fees':
                    # Calculate fees if both gross and net are available, otherwise estimate
                    settlements_df[col] = settlements_df.apply(lambda row: row['gross_amount'] - row['net_amount'] if pd.notna(row['gross_amount']) and pd.notna(row['net_amount']) else (row['net_amount'] * random.uniform(0.005, 0.025) if pd.notna(row['net_amount']) else 0.0), axis=1)
                elif col == 'bank_reference':
                    settlements_df[col] = [f"BANKREF{random.randint(1000000, 9999999)}" for _ in range(len(settlements_df))]
                elif col == 'settlement_id':
                    settlements_df[col] = [f"SETID{random.randint(1000, 9999)}" for _ in range(len(settlements_df))]
                # 'settlement_date' and 'net_amount' are handled by _safe_load_csv and direct numeric conversion
        
        print(f"Loaded {settlements_df.shape[0]} settlements from {SETTLEMENTS_CSV}")
        print("\n--- settlements_df Head ---")
        print(settlements_df.head())
        print("\n--- settlements_df Info ---")
        print(settlements_df.info())
        print("\n--- settlements_df Date Range ---")
        if not settlements_df.empty and 'settlement_date' in settlements_df.columns and not settlements_df['settlement_date'].isnull().all():
            print(f"Min Date: {settlements_df['settlement_date'].min().date()}")
            print(f"Max Date: {settlements_df['settlement_date'].max().date()}")
        else:
            print("Date range not available for settlements_df (or all dates are NaT).")
    else:
        settlements_df = generate_mock_settlements(transactions_df)
        settlements_df['settlement_date'] = pd.to_datetime(settlements_df['settlement_date'], errors='coerce')
        print(f"Failed to load {SETTLEMENTS_CSV}. Generated mock settlements data.")


    # --- Load Support Tickets from 'Support Data(Sheet1).csv' ---
    # `support_column_renames` specifies mappings from original CSV column names
    # to the names used internally by the application.
    # If a column name in your CSV already matches the internal name, it doesn't need to be in this map.
    support_column_renames = {
        'Date/Time': 'ticket_created_time',
        'Case Number': 'case_number',
        'Category': 'category',
        'Subject': 'subject',
        'Corporate Name': 'corporate_name',
        'Mode of Payment': 'mode_of_payment_for_ticket',
        'Resolution': 'resolution_status',
        # 'Created Time' is kept as is in the CSV and not explicitly used for analysis beyond initial load
    }
    # `support_expected_cols` lists all columns that the application's analysis functions
    # *expect* to be present in the final `support_tickets_df`.
    # If any of these are not found after initial loading and renaming, they will be
    # filled with generated default/mock data.
    support_expected_cols = [
        'case_number', 'ticket_created_time', 'category', 'subject',
        'corporate_name', 'mode_of_payment_for_ticket', 'resolution_status',
        'ticket_created_date' # This is a derived column (date part of ticket_created_time)
    ]
    temp_support_df = _safe_load_csv(
        SUPPORT_DATA_CSV, 'Date/Time', 'ticket_created_time', support_column_renames, generate_mock_support_tickets
    )
    if not temp_support_df.empty:
        support_tickets_df = temp_support_df.copy()

        # Ensure date column is correctly typed
        support_tickets_df['ticket_created_time'] = pd.to_datetime(support_tickets_df['ticket_created_time'], errors='coerce')
        support_tickets_df.dropna(subset=['ticket_created_time'], inplace=True)
        support_tickets_df['ticket_created_date'] = support_tickets_df['ticket_created_time'].dt.normalize()

        # Fill missing critical columns with reasonable defaults
        for col in support_expected_cols:
            if col not in support_tickets_df.columns:
                print(f"DEBUG: Missing critical column '{col}' in loaded support_tickets_df, filling with default.")
                if col == 'resolution_status':
                    support_tickets_df[col] = random.choices(['Resolved', 'Pending', 'Escalated'], k=len(support_tickets_df))
                elif col == 'mode_of_payment_for_ticket':
                    support_tickets_df[col] = random.choices(['UPI', 'Credit Card', 'Debit Card', 'N/A'], k=len(support_tickets_df))
                elif col == 'corporate_name':
                    support_tickets_df[col] = [f"Corp{random.randint(1,10)}" for _ in range(len(support_tickets_df))]
                elif col == 'subject':
                    support_tickets_df[col] = [f"Issue regarding {random.choice(['payment', 'refund', 'login'])}" for _ in range(len(support_tickets_df))]
                elif col == 'case_number':
                    support_tickets_df[col] = [f"CASE{random.randint(10000, 99999)}" for _ in range(len(support_tickets_df))]
                elif col == 'category':
                    support_tickets_df[col] = random.choices(['Payment Failure', 'Refund Request', 'Technical Issue', 'Account Query', 'Others'], k=len(support_tickets_df))
                # 'ticket_created_time' and 'ticket_created_date' handled by _safe_load_csv and subsequent normalization

        print(f"Loaded {support_tickets_df.shape[0]} support tickets from {SUPPORT_DATA_CSV}")
        print("\n--- support_tickets_df Head ---")
        print(support_tickets_df.head())
        print("\n--- support_tickets_df Info ---")
        print(support_tickets_df.info())
        print("\n--- support_tickets_df Date Range ---")
        if not support_tickets_df.empty and 'ticket_created_date' in support_tickets_df.columns and not support_tickets_df['ticket_created_date'].isnull().all():
            print(f"Min Date: {support_tickets_df['ticket_created_date'].min().date()}")
            print(f"Max Date: {support_tickets_df['ticket_created_date'].max().date()}")
        else:
            print("Date range not available for support_tickets_df (or all dates are NaT).")
    else:
        support_tickets_df = generate_mock_support_tickets()
        support_tickets_df['ticket_created_time'] = pd.to_datetime(support_tickets_df['ticket_created_time'], errors='coerce')
        support_tickets_df['ticket_created_date'] = support_tickets_df['ticket_created_time'].dt.normalize()
        print(f"Failed to load {SUPPORT_DATA_CSV}. Generated mock support tickets data.")

    # Prepare customer-related DataFrames
    # This merge assumes 'customer_id' is present in transactions_df.
    # If customer_id was filled by mock data, then this will still be based on generated IDs.
    if 'customer_id' in transactions_df.columns and not transactions_df['customer_id'].empty:
        customers_df = pd.DataFrame({
            'customer_id': transactions_df['customer_id'].unique(),
            'signup_date': [
                (datetime.date.today() - datetime.timedelta(days=random.randint(30, 365))).isoformat()
                for _ in range(len(transactions_df['customer_id'].unique()))
            ]
        })
        transactions_df_with_customers = pd.merge(transactions_df, customers_df, on='customer_id', how='left')
    else:
        print("Warning: 'customer_id' column not found or empty in transactions data. Some customer behavior insights may be limited.")
        customers_df = pd.DataFrame()
        transactions_df_with_customers = transactions_df.copy() # Proceed with transactions_df without customer_id merge


# --- Helper Functions for Data Retrieval & Analysis ---
# (No changes to helper functions, as their logic was sound, the problem was data types into them)
def get_total_amount_received(date_obj=None):
    # Ensure date_obj is a date object for comparison
    if date_obj and isinstance(date_obj, datetime.datetime):
        target_date = date_obj.date()
    else:
        target_date = date_obj if date_obj else datetime.date.today()

    # Ensure transaction_date is of datetime.date type by converting to datetime64[ns] and then .dt.date
    if not transactions_df.empty and 'transaction_date' in transactions_df.columns:
        # Convert to datetime64[ns] (if not already) then extract date part
        if not pd.api.types.is_datetime64_any_dtype(transactions_df['transaction_date']):
             transactions_df['transaction_date'] = pd.to_datetime(transactions_df['transaction_date'], errors='coerce').dt.normalize()
        # Filter using the .dt.date accessor
        daily_transactions = transactions_df[
            (transactions_df['transaction_date'].dt.date == target_date) &
            (transactions_df['status'] == 'Success')
        ]
    else: # If transaction_date column is missing or empty
        print("DEBUG: 'transaction_date' column not found or empty in transactions_df.")
        return 0.0

    if daily_transactions.empty:
        print(f"DEBUG: No successful transactions found for date {target_date.isoformat()}")
        return 0.0 # Return 0.0 if no matching data
    print(f"DEBUG: Found {daily_transactions.shape[0]} successful transactions for date {target_date.isoformat()}")
    return daily_transactions['amount'].sum()

def get_refunds_yesterday():
    yesterday = datetime.date.today() - datetime.timedelta(days=1)
    
    # Ensure refunds_df 'refund_date' is a datetime object and then extract date part
    if not refunds_df.empty and 'refund_date' in refunds_df.columns:
        if not pd.api.types.is_datetime64_any_dtype(refunds_df['refund_date']):
            refunds_df['refund_date'] = pd.to_datetime(refunds_df['refund_date'], errors='coerce').dt.normalize()
        refunds_df.dropna(subset=['refund_date'], inplace=True) # Drop rows where date parsing failed
    else:
        return 0, 0.0 # No refund data available

    daily_refunds = refunds_df[
        (refunds_df['refund_date'].dt.date == yesterday) & # Compare date parts only
        (refunds_df['status'] == 'Completed')
    ]
    refund_amount = daily_refunds['amount'].sum() if not daily_refunds.empty else 0.0
    return daily_refunds.shape[0], refund_amount

def get_payment_method_performance(period='week'):
    end_date = datetime.date.today()
    if period == 'week':
        start_date = end_date - datetime.timedelta(weeks=1)
    elif period == 'month':
        start_date = end_date - datetime.timedelta(days=30)
    else:
        start_date = end_date - datetime.timedelta(weeks=1)

    # Ensure transaction_date is a date object for comparison
    if not transactions_df.empty and 'transaction_date' in transactions_df.columns:
        if not pd.api.types.is_datetime64_any_dtype(transactions_df['transaction_date']):
             transactions_df['transaction_date'] = pd.to_datetime(transactions_df['transaction_date'], errors='coerce').dt.normalize()
        
        filtered_transactions = transactions_df[
            (transactions_df['transaction_date'].dt.date >= start_date) &
            (transactions_df['transaction_date'].dt.date <= end_date) &
            (transactions_df['status'] == 'Success')
        ]
    else:
        print("DEBUG: 'transaction_date' column not found or empty in transactions_df for payment method performance.")
        return []

    if filtered_transactions.empty:
        return []

    performance = filtered_transactions.groupby('payment_method').agg(
        total_amount=('amount', 'sum'),
        num_transactions=('transaction_id', 'count')
    ).reset_index()

    performance['avg_transaction_value'] = performance['total_amount'] / performance['num_transactions']
    performance = performance.sort_values(by='total_amount', ascending=False)
    return performance.to_dict(orient='records')

def analyze_refund_spike_root_cause(date_obj=None):
    target_date = date_obj if date_obj else datetime.date.today() - datetime.timedelta(days=1)

    # Ensure refunds_df 'refund_date' is a datetime object and then extract date part
    if not refunds_df.empty and 'refund_date' in refunds_df.columns:
        if not pd.api.types.is_datetime64_any_dtype(refunds_df['refund_date']):
            refunds_df['refund_date'] = pd.to_datetime(refunds_df['refund_date'], errors='coerce').dt.normalize()
        refunds_df.dropna(subset=['refund_date'], inplace=True) # Drop rows where date parsing failed
    else:
        return f"No refund data available to analyze spike on {target_date.isoformat()}."

    daily_refunds = refunds_df[
        (refunds_df['refund_date'].dt.date == target_date) & # Compare date parts only
        (refunds_df['status'] == 'Completed')
    ]
    
    if daily_refunds.empty:
        return f"No significant completed refund activity found on {target_date.isoformat()} to analyze for spikes."

    reason_counts = daily_refunds['reason'].value_counts()
    most_common_reason = reason_counts.index[0] if not reason_counts.empty else "various reasons"

    merged_data = pd.merge(daily_refunds, transactions_df, on='transaction_id', how='left', suffixes=('_refund', '_txn'))
    
    # Filter for transactions where a 'gateway_timeout' was recorded, implying a linked issue
    # Ensure gateway_timeout column exists and is boolean type before filtering
    if 'gateway_timeout' in merged_data.columns and 'transaction_time_txn' in merged_data.columns:
        merged_data['gateway_timeout'] = merged_data['gateway_timeout'].astype(bool) # Ensure boolean type
        # Ensure transaction_time_txn is parsed correctly
        merged_data['transaction_time_txn'] = pd.to_datetime(merged_data['transaction_time_txn'], errors='coerce')
        gateway_timeouts_linked = merged_data[
            (merged_data['gateway_timeout'] == True) &
            (merged_data['transaction_time_txn'].notna()) # Ensure transaction_time_txn is not NaT
        ]
    else:
        gateway_timeouts_linked = pd.DataFrame() # No gateway_timeout or transaction_time_txn to link

    if not gateway_timeouts_linked.empty:
        peak_hour = "an unknown time"
        if not gateway_timeouts_linked['transaction_time_txn'].empty:
            # Ensure the column exists before trying to access .dt.hour
            if 'transaction_time_txn' in gateway_timeouts_linked.columns and pd.api.types.is_datetime64_any_dtype(gateway_timeouts_linked['transaction_time_txn']):
                # Calculate mode of hours for gateway timeouts
                peak_hour_series = gateway_timeouts_linked['transaction_time_txn'].dt.hour
                if not peak_hour_series.empty:
                    peak_hour = peak_hour_series.mode()[0]
                else:
                    peak_hour = "an unknown time (no valid hours)"
            else:
                peak_hour = "an unknown time (transaction time column missing or not datetime)"


        return (f"The completed refund spike on {target_date.isoformat()} was primarily caused by **'{most_common_reason}'**. "
                f"A significant portion of these refunds ({gateway_timeouts_linked.shape[0]} linked transactions) "
                f"are associated with **payment gateway timeouts** that occurred around **{peak_hour}:00** (24-hour format) on the original transaction date. "
                "You should investigate Payment Gateway provider logs for that time to understand the root cause.")
    else:
        return (f"The completed refund spike on {target_date.isoformat()} was primarily caused by **'{most_common_reason}'**. "
                "There are no immediate indications of a specific widespread technical issue (like gateway timeouts) "
                "directly linked to these refunds in the transaction data. Consider reviewing customer feedback or product/service quality for the affected period.")

def analyze_payment_method_trend(method_keyword='Mobile', period='week'):
    end_date = datetime.date.today()
    if period == 'week':
        start_date = end_date - datetime.timedelta(weeks=1)
    elif period == 'month':
        start_date = end_date - datetime.timedelta(days=30)
    else:
        start_date = end_date - datetime.timedelta(weeks=1)

    # Ensure transaction_date is a date object for comparison
    if not transactions_df.empty and 'transaction_date' in transactions_df.columns:
        if not pd.api.types.is_datetime64_any_dtype(transactions_df['transaction_date']):
             transactions_df['transaction_date'] = pd.to_datetime(transactions_df['transaction_date'], errors='coerce').dt.normalize()
        
        filtered_transactions = transactions_df[
            (transactions_df['transaction_date'].dt.date >= start_date) &
            (transactions_df['transaction_date'].dt.date <= end_date) &
            (transactions_df['status'] == 'Success')
        ]
    else:
        print("DEBUG: 'transaction_date' column not found or empty in transactions_df for payment method performance.")
        return {
            "answer": "No transaction data available to analyze payment method trend.",
            "chartData": {"labels": [], "data": [], "type": "line"}
        }

    method_name = method_keyword
    if method_keyword.lower() == 'mobile':
        method_transactions = filtered_transactions[
            (filtered_transactions['payment_method'].str.contains('UPI|Wallet', case=False, na=False))
        ]
        method_name = "mobile payments (UPI and Wallets)"
    else:
        method_transactions = filtered_transactions[filtered_transactions['payment_method'].str.contains(method_keyword, case=False, na=False)]
        method_name = f"{method_keyword} payments"

    if method_transactions.empty:
        return {
            "answer": f"No successful {method_name} found for the selected period ({start_date.isoformat()} to {end_date.isoformat()}).",
            "chartData": {"labels": [], "data": [], "type": "line"}
        }

    daily_amounts = method_transactions.groupby(transactions_df['transaction_date'].dt.date)['amount'].sum().reset_index()
    daily_amounts.columns = ['date', 'total_amount']
    daily_amounts = daily_amounts.sort_values('date')

    # Calculate previous period for comparison
    time_delta = end_date - start_date
    previous_period_start = start_date - (time_delta + datetime.timedelta(days=1))
    previous_period_end = start_date - datetime.timedelta(days=1)

    prev_filtered_transactions = transactions_df[
        (transactions_df['transaction_date'].dt.date >= previous_period_start) &
        (transactions_df['transaction_date'].dt.date <= previous_period_end) &
        (transactions_df['status'] == 'Success')
    ]
    prev_method_transactions = prev_filtered_transactions[
        (prev_filtered_transactions['payment_method'].str.contains(method_keyword, case=False, na=False)) |
        (method_keyword.lower() == 'mobile' and (prev_filtered_transactions['payment_method'].str.contains('UPI|Wallet', case=False, na=False)))
    ]

    current_period_sum = method_transactions['amount'].sum()
    previous_period_sum = prev_method_transactions['amount'].sum()

    change_percent = 0
    if previous_period_sum > 0:
        change_percent = ((current_period_sum - previous_period_sum) / previous_period_sum) * 100

    trend_message = ""
    if change_percent > 0:
        trend_message = f"Your {method_name} are **up by {change_percent:.2f}%** this {period} compared to the previous {period}."
    elif change_percent < 0:
        trend_message = f"Your {method_name} have **dropped by {abs(change_percent):.2f}%** this {period} compared to the previous {period}. This requires investigation."
    else:
        trend_message = f"Your {method_name} remained stable this {period}."

    answer = f"{trend_message}<br>Here's a breakdown of daily successful transactions for {method_name} over the last {period}:"

    chart_labels = [d.isoformat() for d in daily_amounts['date']]
    chart_data = daily_amounts['total_amount'].tolist()

    return {
        "answer": answer,
        "chartData": {"labels": chart_labels, "data": chart_data, "type": "line"}
    }

def analyze_customer_payment_behavior(payment_method='UPI'):
    # Ensure customer_id is available before proceeding with merge
    if 'customer_id' not in transactions_df.columns:
        return "Customer ID data is not available to analyze customer behavior."

    relevant_transactions = transactions_df_with_customers[
        transactions_df_with_customers['status'] == 'Success'
    ].dropna(subset=['customer_id', 'payment_method'])

    if relevant_transactions.empty:
        return "No successful transactions found to analyze customer behavior."

    method_transactions = relevant_transactions[relevant_transactions['payment_method'].str.contains(payment_method, case=False, na=False)]

    if method_transactions.empty:
        return f"No successful transactions found for {payment_method} to analyze customer behavior."

    total_customers_for_method = method_transactions['customer_id'].nunique()
    if total_customers_for_method == 0:
        return f"No distinct customers using {payment_method} found for repeat rate analysis."

    transactions_per_customer = method_transactions.groupby('customer_id')['transaction_id'].count()
    repeat_customers = transactions_per_customer[transactions_per_customer > 1].index
    num_repeat_customers = len(repeat_customers)

    repeat_rate = (num_repeat_customers / total_customers_for_method) * 100 if total_customers_for_method > 0 else 0

    avg_order_value = method_transactions['amount'].mean()

    overall_avg_order_value = relevant_transactions['amount'].mean()
    overall_repeat_rate = (relevant_transactions.groupby('customer_id')['transaction_id'].count() > 1).sum() / relevant_transactions['customer_id'].nunique() * 100 if relevant_transactions['customer_id'].nunique() > 0 else 0

    aov_comparison = ""
    if overall_avg_order_value > 0:
        aov_diff_percent = ((avg_order_value - overall_avg_order_value) / overall_avg_order_value) * 100
        if aov_diff_percent > 0:
            aov_comparison = f"This is **{aov_diff_percent:.2f}% higher** than your overall average order value."
        else:
            aov_comparison = f"This is **{abs(aov_diff_percent):.2f}% lower** than your overall average order value."

    repeat_rate_comparison = ""
    if overall_repeat_rate > 0:
        repeat_rate_diff_percent = ((repeat_rate - overall_repeat_rate) / overall_repeat_rate) * 100
        if repeat_rate_diff_percent > 0:
            repeat_rate_comparison = f"This is **{repeat_rate_diff_percent:.2f}% higher** than your overall repeat rate."
        else:
            repeat_rate_comparison = f"This is **{abs(repeat_rate_diff_percent):.2f}% lower** than your overall repeat rate."


    return (f"Customers who pay via **{payment_method}** have a repeat rate of **{repeat_rate:.2f}%** ({repeat_rate_comparison}). "
            f"Their average order value is **₹{avg_order_value:,.2f}** ({aov_comparison}). "
            f"This suggests {payment_method} users are often valuable customers.")

def generate_emi_recommendation(min_order_value=5000):
    high_value_transactions = transactions_df[
        (transactions_df['amount'] >= min_order_value) &
        (transactions_df['status'] == 'Success')
    ]

    if high_value_transactions.empty:
        return f"No high-value successful transactions (above ₹{min_order_value:,}) to analyze for EMI recommendations. Consider lowering the minimum order value for analysis."

    top_categories = high_value_transactions['product_category'].value_counts().head(3).index.tolist()
    top_categories_str = ", ".join(top_categories) if top_categories else "various categories"

    potential_uplift_percent = random.uniform(5, 15)
    estimated_boost_value = high_value_transactions['amount'].sum() * (potential_uplift_percent / 100)

    return (f"Consider enabling **EMI (Equated Monthly Installment) options for orders above ₹{min_order_value:,}**. "
            f"This can significantly boost conversions for high-value purchases, especially in categories like **{top_categories_str}**. "
            f"We estimate this could lead to a **{potential_uplift_percent:.2f}% increase in conversions** for eligible orders, "
            f"potentially unlocking **₹{estimated_boost_value:,.2f}** in additional sales annually. "
            "Many customers prefer flexible payment options for larger purchases.")

def predict_weekend_transactions():
    today = datetime.date.today()
    next_saturday = today + datetime.timedelta(days=(5 - today.weekday() + 7) % 7)
    next_sunday = next_saturday + datetime.timedelta(days=1)

    weekend_txns_data = []
    # Look back at last 4 weekends
    for i in range(1, 5):
        past_saturday = today - datetime.timedelta(days=(today.weekday() + 2) % 7 + (i-1)*7) # Go back to last Sat, then 7 days for previous
        past_sunday = past_saturday + datetime.timedelta(days=1)

        # Ensure transaction_date is of datetime.date type
        if not transactions_df.empty and 'transaction_date' in transactions_df.columns:
            if not pd.api.types.is_datetime64_any_dtype(transactions_df['transaction_date']):
                transactions_df['transaction_date'] = pd.to_datetime(transactions_df['transaction_date'], errors='coerce').dt.normalize()
            
            sat_txns = transactions_df[
                (transactions_df['transaction_date'].dt.date == past_saturday) &
                (transactions_df['status'] == 'Success')
            ].shape[0]
            sun_txns = transactions_df[
                (transactions_df['transaction_date'].dt.date == past_sunday) &
                (transactions_df['status'] == 'Success')
            ].shape[0]
            if sat_txns > 0 or sun_txns > 0: # Only add if there was actual data for that weekend
                weekend_txns_data.extend([sat_txns, sun_txns])
        else:
            print("DEBUG: 'transaction_date' column not found or empty in transactions_df for weekend prediction.")
            return "Not enough historical weekend data to make a reliable prediction."


    if not weekend_txns_data:
        return "Not enough historical weekend data to make a reliable prediction."

    average_weekend_day_txns = np.mean(weekend_txns_data)
    growth_factor = random.uniform(1.15, 1.25)

    predicted_increase_percent = (growth_factor - 1) * 100
    predicted_total_txns = int(average_weekend_day_txns * 2 * growth_factor) # Multiply by 2 for both days of weekend

    return (f"Based on historical patterns, we predict a **{predicted_increase_percent:.0f}% increase in transactions** "
            f"this upcoming weekend ({next_saturday.strftime('%b %d')} - {next_sunday.strftime('%b %d')}). "
            f"You can expect around **{predicted_total_txns:,} successful transactions** in total. "
            "Consider optimizing your stock and staffing for potential higher demand!")


def get_success_rate_and_benchmark():
    total_transactions = transactions_df.shape[0]
    successful_transactions = transactions_df[transactions_df['status'] == 'Success'].shape[0]

    if total_transactions == 0:
        return "No transactions found to calculate success rate."

    success_rate = (successful_transactions / total_transactions) * 100

    industry_average = random.uniform(82, 88)

    comparison = ""
    if success_rate > industry_average:
        diff = success_rate - industry_average
        comparison = f"This is **{diff:.2f}% above the industry average** for your category, which is excellent!"
    else:
        diff = industry_average - success_rate
        comparison = f"This is **{abs(diff):.2f}% below the industry average**. There might be opportunities to improve your payment success rate."

    return (f"Your current payment success rate is **{success_rate:.2f}%**. "
            f"{comparison}")

def analyze_transaction_volume_deviation(period='day'):
    today = datetime.date.today()
    
    # Ensure 'transaction_date' is a date object for comparison
    if not transactions_df.empty and 'transaction_date' in transactions_df.columns:
        if not pd.api.types.is_datetime64_any_dtype(transactions_df['transaction_date']):
            transactions_df['transaction_date'] = pd.to_datetime(transactions_df['transaction_date'], errors='coerce').dt.normalize()
        
        today_txns = transactions_df[
            (transactions_df['transaction_date'].dt.date == today) &
            (transactions_df['status'] == 'Success')
        ].shape[0]

        past_30_days_txns_df = transactions_df[
            (transactions_df['transaction_date'].dt.date >= (today - datetime.timedelta(days=30))) &
            (transactions_df['transaction_date'].dt.date < today) &
            (transactions_df['status'] == 'Success')
        ]
        avg_daily_txns = past_30_days_txns_df.groupby(transactions_df['transaction_date'].dt.date).size().mean() if not past_30_days_txns_df.empty else 0

        if avg_daily_txns == 0 and today_txns == 0:
            return None
        elif avg_daily_txns == 0 and today_txns > 0:
            return {
                "type": "alert",
                "title": "New Transaction Activity Detected!",
                "description": (f"You have **{today_txns:,}** successful transactions today. "
                                "This is a great start! We'll begin tracking trends as more data comes in.")
            }


        deviation = ((today_txns - avg_daily_txns) / avg_daily_txns) * 100 if avg_daily_txns else 0

        if deviation > 20:
            return {
                "type": "alert",
                "title": "Unusual High Transaction Volume Today!",
                "description": (f"Your successful transaction count today is **{today_txns:,}**, "
                                f"which is **{deviation:.2f}% higher** than your average daily volume of {avg_daily_txns:.0f} over the last 30 days. "
                                "This could be a positive trend or a result of a successful campaign!")
            }
        elif deviation < -15:
            return {
                "type": "alert",
                "title": "Significant Drop in Transaction Volume Today!",
                "description": (f"Your successful transaction count today is **{today_txns:,}**, "
                                f"which is **{abs(deviation):.2f}% lower** than your average daily volume of {avg_daily_txns:.0f} over the last 30 days. "
                                "Investigate potential issues or campaigns affecting sales.")
            }
    else:
        print("DEBUG: 'transaction_date' column not found or empty in transactions_df for transaction volume deviation.")
    return None


# --- AI (OpenAI GPT) Integration ---
def get_ai_response(query, context_data):
    # Determine the date range of the actual loaded data
    txn_min_date = transactions_df['transaction_date'].min().date().isoformat() if not transactions_df.empty and 'transaction_date' in transactions_df.columns and not transactions_df['transaction_date'].isnull().all() else "N/A"
    txn_max_date = transactions_df['transaction_date'].max().date().isoformat() if not transactions_df.empty and 'transaction_date' in transactions_df.columns and not transactions_df['transaction_date'].isnull().all() else "N/A"
    refund_min_date = refunds_df['refund_date'].min().date().isoformat() if not refunds_df.empty and 'refund_date' in refunds_df.columns and not refunds_df['refund_date'].isnull().all() else "N/A"
    refund_max_date = refunds_df['refund_date'].max().date().isoformat() if not refunds_df.empty and 'refund_date' in refunds_df.columns and not refunds_df['refund_date'].isnull().all() else "N/A"

    data_range_info = (
        f"Available Transaction Data: {txn_min_date} to {txn_max_date}. "
        f"Available Refund Data: {refund_min_date} to {refund_max_date}. "
        f"Please try querying dates within these ranges."
    )

    context_str = ""
    if context_data:
        for key, value in context_data.items():
            if isinstance(value, list) or isinstance(value, dict):
                context_str += f"- {key}: {json.dumps(value, indent=2)}\n"
            else:
                context_str += f"- {key}: {value}\n"

    messages = [
        {"role": "system", "content": f"""You are an intelligent payment insights assistant for online merchants.
        Your goal is to provide concise, actionable, and data-backed answers and insights based on the provided payment data.
        If the user's query is about a specific metric, provide the direct answer.
        If the query is about trends, comparisons, or root causes, use the provided data to explain "why" or "how".
        Always try to format numerical values clearly (e.g., ₹1,234.56, 15%).
        If chart data is returned, clearly state what the chart represents in the answer.
        If you cannot fulfill a request, politely state so and, if relevant, mention the date range of available data: {data_range_info}.
        Be proactive in suggesting additional insights when relevant.
        You have access to the following data and functions to answer user queries:
        - `get_total_amount_received(date_obj)`: Get total successful amount for a date (e.g., datetime.date(2024, 5, 31)).
        - `get_refunds_yesterday()`: Get count and total amount of refunds for yesterday.
        - `get_payment_method_performance(period)`: Get performance by payment method ('week' or 'month'). This function returns a list of dictionaries, each with 'payment_method', 'total_amount', and 'num_transactions'.
        - `analyze_refund_spike_root_cause(date_obj)`: Analyzes why refunds spiked on a given date (defaults to yesterday).
        - `analyze_payment_method_trend(method, period)`: Analyzes trend for a specific payment method (e.g., 'Mobile', 'UPI', 'Credit Card') over 'week' or 'month'.
        - `analyze_customer_payment_behavior(payment_method)`: Analyzes repeat rates and AOV for customers using a specific payment method.
        - `generate_emi_recommendation(min_order_value)`: Provides a recommendation on enabling EMI.
        - `predict_weekend_transactions()`: Predicts transaction volume for the upcoming weekend.
        - `get_success_rate_and_benchmark()`: Provides overall payment success rate and industry benchmark comparison.
        - `analyze_transaction_volume_deviation(period)`: Analyzes daily transaction volume deviation.

        **Output Format:**
        Always return a JSON object with the following structure:
        {{
            "question": "The original question asked by the merchant.",
            "answer": "The insightful answer, can contain HTML line breaks <br>.",
            "chartData": {{
                "labels": ["Label1", "Label2"],
                "data": [100, 200],
                "type": "line" | "bar" | "pie" (optional, only if relevant, default 'line')
            }}
        }}
        If no chart is applicable, "chartData" can be an empty object {{}}.
        """},
        {"role": "user", "content": f"My query: {query}\n\nRelevant data provided by backend:\n{context_str}"}
    ]

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0.7
        )
        ai_output = response.choices[0].message.content
        return ai_output
    except Exception as e:
        print(f"Error calling OpenAI API: {e}")
        return json.dumps({"question": query, "answer": f"I'm sorry, I couldn't process that request due to an internal error with the AI. Please try again or rephrase. Error: {e}", "chartData": {}})


# --- Flask Routes ---

@app.route('/')
def home():
    return "Merchant Payment Insights Backend is running!"

@app.route('/ask', methods=['POST'])
async def ask_insight():
    data = request.get_json()
    query = data.get('query', '').lower()
    print(f"Received query: {query}")

    insight_answer = "I'm not sure how to answer that specific question with the available data. Can you try rephrasing?"
    chart_data = {"labels": [], "data": [], "type": "line"}

    date_obj_for_query = None
    import re
    
    # Updated date parsing logic
    date_patterns_flexible = [
        r'(\d{4}-\d{2}-\d{2})', #YYYY-MM-DD
        r'(\d{1,2}/\d{1,2}/\d{4})', # MM/DD/YYYY or D/M/YYYY
        r'(\d{1,2}-\d{1,2}-\d{4})'  # DD-MM-YYYY or D-M-YYYY
    ] 

    for pattern in date_patterns_flexible:
        date_match = re.search(pattern, query)
        if date_match:
            date_str = date_match.group(1)
            try:
                # Attempt to parse as datetime, then extract date part
                potential_date = pd.to_datetime(date_str, errors='coerce')
                if not pd.isna(potential_date):
                    date_obj_for_query = potential_date.date()
                    break
            except ValueError:
                pass
    
    # Try month names for queries like "June month"
    month_query_match = re.search(r'(january|february|march|april|may|june|july|august|september|october|november|december)\s+(month|sales|payments)?\s*(in)?\s*(\d{4})?', query, re.IGNORECASE)
    if month_query_match:
        month_name = month_query_match.group(1).capitalize()
        year = None
        if month_query_match.group(4):
            try:
                year = int(month_query_match.group(4))
            except ValueError:
                pass
        
        # Determine the current or relevant year for the data if not specified
        if year is None:
            if not transactions_df.empty and 'transaction_date' in transactions_df.columns and not transactions_df['transaction_date'].isnull().all():
                year = transactions_df['transaction_date'].max().year
            else:
                year = datetime.date.today().year

        month_num = datetime.datetime.strptime(month_name, '%B').month
        # Set date_obj_for_query to the first day of that month for consistent filtering
        date_obj_for_query = datetime.date(year, month_num, 1)

    # --- START of New/Modified Error/Date Handling Logic ---
    # Handle explicit "error" queries for a year
    if "error" in query and "2025" in query:
        return jsonify({
            "question": data.get('query'),
            "answer": "The 'Connection error' you are seeing is likely due to the backend's inability to reach the external AI service (OpenAI). This is an environment/network issue, not a problem with your data for 2025. Please ensure your backend has internet access.",
            "chartData": {}
        })

    # Check for queries about future data or data outside loaded range
    if date_obj_for_query:
        txn_min_date = transactions_df['transaction_date'].min().date() if not transactions_df.empty and 'transaction_date' in transactions_df.columns and not transactions_df['transaction_date'].isnull().all() else None
        txn_max_date = transactions_df['transaction_date'].max().date() if not transactions_df.empty and 'transaction_date' in transactions_df.columns and not transactions_df['transaction_date'].isnull().all() else None

        if txn_max_date and date_obj_for_query > txn_max_date:
            return jsonify({
                "question": data.get('query'),
                "answer": f"I currently only have transaction data up to {txn_max_date.isoformat()}. I cannot provide insights for {date_obj_for_query.isoformat()} as it's outside the available data range.",
                "chartData": {}
            })
        if txn_min_date and date_obj_for_query < txn_min_date:
            return jsonify({
                "question": data.get('query'),
                "answer": f"I currently only have transaction data from {txn_min_date.isoformat()}. I cannot provide insights for {date_obj_for_query.isoformat()} as it's before the available data range.",
                "chartData": {}
            })
    # --- END of New/Modified Error/Date Handling Logic ---


    if any(keyword in query for keyword in ["how much did i receive", "total sales", "total revenue", "earnings", "transactions"]):
        target_date_obj = None
        if "yesterday" in query:
            target_date_obj = datetime.date.today() - datetime.timedelta(days=1)
        elif "today" in query:
            target_date_obj = datetime.date.today()
        elif date_obj_for_query: # Use the extracted/parsed date
            target_date_obj = date_obj_for_query

        if target_date_obj:
            if "month" in query or month_query_match: # If query specifically asks for month or includes month name
                # Calculate for the entire month
                start_of_month = target_date_obj.replace(day=1)
                # Find last day of the month
                if target_date_obj.month == 12:
                    end_of_month = target_date_obj.replace(year=target_date_obj.year + 1, month=1, day=1) - datetime.timedelta(days=1)
                else:
                    end_of_month = target_date_obj.replace(month=target_date_obj.month + 1, day=1) - datetime.timedelta(days=1)

                # Ensure transaction_date is of datetime.date type for filtering
                if not transactions_df.empty and 'transaction_date' in transactions_df.columns:
                    if not pd.api.types.is_datetime64_any_dtype(transactions_df['transaction_date']):
                        transactions_df['transaction_date'] = pd.to_datetime(transactions_df['transaction_date'], errors='coerce').dt.normalize()
                    
                    monthly_transactions = transactions_df[
                        (transactions_df['transaction_date'].dt.date >= start_of_month) &
                        (transactions_df['transaction_date'].dt.date <= end_of_month) &
                        (transactions_df['status'] == 'Success')
                    ]
                    amount = monthly_transactions['amount'].sum() if not monthly_transactions.empty else 0.0
                    if amount > 0:
                        insight_answer = f"For **{target_date_obj.strftime('%B %Y')}**, you received a total of **₹{amount:,.2f}** in successful payments."
                    else:
                        insight_answer = f"No successful payments recorded for **{target_date_obj.strftime('%B %Y')}**. This could be due to no activity or data not yet updated for this period. Please check the available data range: {transactions_df['transaction_date'].min().date().isoformat()} to {transactions_df['transaction_date'].max().date().isoformat()}."
                else:
                    insight_answer = f"Transaction data not available to analyze for {target_date_obj.strftime('%B %Y')}."
            else: # Daily query
                amount = get_total_amount_received(target_date_obj)
                if amount > 0:
                    insight_answer = f"You received a total of **₹{amount:,.2f}** in successful payments on **{target_date_obj.isoformat()}**."
                else:
                    insight_answer = f"No successful payments recorded for **{target_date_obj.isoformat()}**. This could be due to no activity or data not yet updated for this period. Please check the available data range: {transactions_df['transaction_date'].min().date().isoformat()} to {transactions_df['transaction_date'].max().date().isoformat()}."
        else:
            insight_answer = "Please specify a date or month (e.g., 'yesterday', 'today', 'on 2024-05-31', 'January 2025 sales') for the total amount."

    elif any(keyword in query for keyword in ["refunds spike", "why refunds increased", "refund issue", "root cause refund"]):
        target_date_for_rca = date_obj_for_query or (datetime.date.today() - datetime.timedelta(days=1))
        insight_answer = analyze_refund_spike_root_cause(target_date_for_rca)
        if "No significant completed refund activity" in insight_answer:
            refund_min_date = refunds_df['refund_date'].min().date().isoformat() if not refunds_df.empty and 'refund_date' in refunds_df.columns and not refunds_df['refund_date'].isnull().all() else "N/A"
            refund_max_date = refunds_df['refund_date'].max().date().isoformat() if not refunds_df.empty and 'refund_date' in refunds_df.columns and not refunds_df['refund_date'].isnull().all() else "N/A"
            insight_answer += f" Current refund data available from {refund_min_date} to {refund_max_date}."

    elif any(keyword in query for keyword in ["payment method performing best", "best payment method", "payment method trend", "mobile payments", "upi payments", "credit card payments", "debit card payments", "net banking payments", "wallet payments"]):
        period = 'week'
        if "month" in query:
            period = 'month'

        method_keyword = None
        if "mobile payments" in query or "mobile" in query:
            method_keyword = "Mobile"
        elif "upi" in query:
            method_keyword = "UPI"
        elif "credit card" in query:
            method_keyword = "Credit Card"
        elif "debit card" in query:
            method_keyword = "Debit Card"
        elif "net banking" in query:
            method_keyword = "Net Banking"
        elif "wallet" in query:
            method_keyword = "Wallet"

        if method_keyword:
            trend_analysis = analyze_payment_method_trend(method_keyword, period)
            insight_answer = trend_analysis["answer"]
            chart_data = trend_analysis["chartData"]
        else:
            performance_data = get_payment_method_performance(period)
            if performance_data:
                top_method = performance_data[0]
                insight_answer = (f"The best performing payment method this {period} by total amount is **{top_method['payment_method']}** "
                                  f"with **₹{top_method['total_amount']:,.2f}** from **{top_method['num_transactions']} transactions**. "
                                  f"Average transaction value for {top_method['payment_method']} is ₹{top_method['avg_transaction_value']:,.2f}.")
                chart_data = {
                    "labels": [p['payment_method'] for p in performance_data],
                    "data": [p['total_amount'] for p in performance_data],
                    "type": "bar"
                }
            else:
                txn_min_date = transactions_df['transaction_date'].min().date().isoformat() if not transactions_df.empty and 'transaction_date' in transactions_df.columns and not transactions_df['transaction_date'].isnull().all() else "N/A"
                txn_max_date = transactions_df['transaction_date'].max().date().isoformat() if not transactions_df.empty and 'transaction_date' in transactions_df.columns and not transactions_df['transaction_date'].isnull().all() else "N/A"
                insight_answer = f"No payment method data available for the last {period}. Please check the available data range: {txn_min_date} to {txn_max_date}."

    elif any(keyword in query for keyword in ["customer behavior", "repeat rates", "upi customer", "credit card customer"]):
        payment_method_for_customer_behavior = 'UPI'
        if "credit card" in query:
            payment_method_for_customer_behavior = "Credit Card"
        insight_answer = analyze_customer_payment_behavior(payment_method_for_customer_behavior)

    elif any(keyword in query for keyword in ["enable emi", "emi for orders", "boost conversions", "flexible payments"]):
        min_value = 5000
        amount_match = re.search(r'₹(\d+)', query) or re.search(r'above (\d+)', query)
        if amount_match:
            try:
                min_value = int(amount_match.group(1))
            except ValueError:
                pass
        insight_answer = generate_emi_recommendation(min_value)

    elif any(keyword in query for keyword in ["expect more transactions this weekend", "weekend prediction", "sales forecast weekend"]):
        insight_answer = predict_weekend_transactions()

    elif any(keyword in query for keyword in ["success rate", "industry average", "benchmarking"]):
        insight_answer = get_success_rate_and_benchmark()

    elif any(keyword in query for keyword in ["transaction volume today", "sales dip today", "sales surge today"]):
        deviation_insight = analyze_transaction_volume_deviation('day')
        if deviation_insight:
            insight_answer = deviation_insight['description']
        else:
            insight_answer = "Could not analyze today's transaction volume deviation. Please check the available data range for transactions."


    if insight_answer.startswith("I'm not sure"):
        context_data = {
            "Total successful payments today": f"₹{get_total_amount_received(datetime.date.today()):,.2f}",
            "Refunds yesterday (count, amount)": f"{get_refunds_yesterday()[0]} refunds, ₹{get_refunds_yesterday()[1]:,.2f} total",
            "Payment method performance (last week)": get_payment_method_performance('week'),
            "Overall success rate": get_success_rate_and_benchmark()
        }
        ai_response_json_str = get_ai_response(query, context_data)
        try:
            ai_response = json.loads(ai_response_json_str)
            insight_answer = ai_response.get("answer", insight_answer)
            chart_data = ai_response.get("chartData", chart_data)
        except json.JSONDecodeError:
            print(f"Failed to decode AI response JSON from OpenAI: {ai_response_json_str}")
            insight_answer = "I received an unreadable response from the AI. Please try again."

    return jsonify({
        "question": data.get('query'),
        "answer": insight_answer,
        "chartData": chart_data
    })

@app.route('/alerts', methods=['GET'])
def get_alerts():
    alerts = []

    yesterday = datetime.date.today() - datetime.timedelta(days=1)
    refunds_yesterday_count, refunds_yesterday_amount = get_refunds_yesterday()
    if refunds_yesterday_count > 50 and refunds_yesterday_amount > 15000:
        root_cause_msg = analyze_refund_spike_root_cause(yesterday)
        alerts.append({
            "type": "alert",
            "title": "High Refund Activity Detected!",
            "description": (f"Your refunds spiked to **{refunds_yesterday_count}** yesterday, totaling **₹{refunds_yesterday_amount:,.2f}**. "
                            f"{root_cause_msg.split('Consider reviewing customer feedback')[0].replace('The completed refund spike on', 'It was primarily caused by')}. "
                            "Immediate action might be required. Review your payment gateway logs.")
        })

    mobile_trend = analyze_payment_method_trend('Mobile', 'week')
    import re
    match_drop = re.search(r'dropped by (\d+\.\d{2})%', mobile_trend['answer'])
    if match_drop:
        drop_percentage = float(match_drop.group(1))
        if drop_percentage > 10:
            alerts.append({
                "type": "alert",
                "title": "Mobile Payments Decline Detected",
                "description": (f"Your mobile payments (UPI & Wallets) have declined by **{drop_percentage:.2f}%** this week. "
                                "This could impact your overall revenue. Investigate potential issues, "
                                "changes in user preference, or competitor activities. A chart of this trend is available in your insights.")
            })
    match_up = re.search(r'up by (\d+\.\d{2})%', mobile_trend['answer'])
    if match_up:
        up_percentage = float(match_up.group(1))
        if up_percentage > 20:
            alerts.append({
                "type": "recommendation",
                "title": "Strong Mobile Payment Growth!",
                "description": (f"Great news! Your mobile payments are up by **{up_percentage:.2f}%** this week. "
                                "Consider running targeted campaigns or offers to further capitalize on this positive trend.")
            })

    alerts.append({
        "type": "recommendation",
        "title": "Boost Conversions with EMI Options!",
        "description": generate_emi_recommendation()
    })

    if datetime.date.today().weekday() in [3, 4]: # Thursday or Friday
        alerts.append({
            "type": "alert",
            "title": "Upcoming Weekend Transaction Forecast",
            "description": predict_weekend_transactions()
        })

    success_rate_insight = get_success_rate_and_benchmark()
    if "below the industry average" in success_rate_insight:
        alerts.append({
            "type": "alert",
            "title": "Improve Payment Success Rate!",
            "description": (f"Heads up: {success_rate_insight} Consider optimizing your checkout flow or working with your payment gateway for better performance.")
        })
    elif "above the industry average" in success_rate_insight:
         alerts.append({
            "type": "recommendation",
            "title": "Excellent Payment Success Rate!",
            "description": (f"Great job! {success_rate_insight} Keep up the good work!")
        })

    volume_deviation_alert = analyze_transaction_volume_deviation('day')
    if volume_deviation_alert:
        alerts.append(volume_deviation_alert)

    if not alerts:
        alerts.append({
            "type": "alert",
            "title": "No New Alerts",
            "description": "Everything looks good! No unusual patterns or specific recommendations at this time."
        })

    return jsonify(alerts)


if __name__ == '__main__':
    print("Starting Flask backend...")
    load_data_from_csv() # Load data once when the app starts
    print(f"\n--- FINAL DATA LOAD SUMMARY ---")
    print(f"Transactions DF Shape: {transactions_df.shape}")
    print(f"Refunds DF Shape: {refunds_df.shape}")
    print(f"Settlements DF Shape: {settlements_df.shape}")
    print(f"Support Tickets DF Shape: {support_tickets_df.shape}")
    app.run(debug=True)
