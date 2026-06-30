# Merchant Payment Insights Dashboard

This project provides a web-based dashboard for merchants to gain quick, conversational insights into their payment data using a natural language interface. Leveraging a Flask backend for data processing and integration with xAI's Grok API for intelligent responses, it allows users to ask questions about transactions, refunds, and performance, receiving data-backed answers and visualizations.

## ✨ Features

* **Conversational AI:** Ask questions about your payment data in plain English.
* **Transaction Analysis:** Get insights into successful payments, total revenue, and transaction volumes for specific dates or periods.
* **Refund Management:** Analyze refund trends, identify spikes, and understand root causes.
* **Payment Method Performance:** Evaluate which payment methods are performing best and track their trends over time.
* **Customer Behavior Insights:** Understand repeat rates and average order values for customers using different payment methods.
* **Proactive Alerts & Recommendations:** Receive automated alerts on unusual activity (e.g., high refunds, significant sales dips/surges) and recommendations (e.g., EMI options, weekend sales forecasts).
* **Dynamic Charting:** Visualize key metrics with interactive line, bar, and pie charts generated directly from your data.
* **Light/Dark Mode:** A customizable theme for better user experience.
* **PDF Export:** Download a summary of your insights and alerts.
* **Secure Login:** Basic authentication to access the dashboard.

#🚀 Technologies Used

**Backend:**
* **Python 3:** The core language for the backend logic.
* **Flask:** A lightweight web framework for building the API.
* **Pandas:** For efficient data loading, manipulation, and analysis of CSV files.
* **OpenAI Python Client (pointed at xAI):** Used to interact with xAI's Grok model (Grok exposes an OpenAI-compatible API) for natural language processing and generating insightful responses.

**Frontend:**
* **HTML5:** Structure of the web application.
* **CSS3:** Custom styling for a modern and responsive user interface.
* **JavaScript:** For dynamic content, user interaction, and fetching data from the Flask backend.
* **Chart.js:** A powerful JavaScript library for rendering various types of charts and graphs.
* **jsPDF:** For generating PDF reports of the insights.
* **Google Fonts (Poppins):** For enhanced typography.

#📦 Data Files

This application relies on the following CSV files, which should be placed in the root directory alongside `app.py`:

* `settlement_data.csv`: Contains primary transaction and settlement records.
* `txn_refunds.csv`: Contains details about transaction refunds.
* `Support Data(Sheet1).csv`: Contains customer support ticket data.

_Note: If CSVs are missing or problematic, the backend generates mock data to ensure basic functionality._

## ⚙️ Setup and Installation

Follow these steps to get your Merchant Payment Insights Dashboard up and running:

### 1. Clone the Repository

git clone https://github.com/prnvshlk7777/pl_online_hackathon_2025
cd airtribe-hackathon


### 2. Set up Python Backend

It's recommended to use a Python virtual environment.

# Create a virtual environment

python -m venv venv

# Activate the virtual environment

# On Windows:

.\\venv\\Scripts\\activate

# On macOS/Linux:

source venv/bin/activate

# Install backend dependencies

pip install -r requirements.txt

3. Place Your Data Files
Ensure the settlement_data.csv, txn_refunds.csv, and Support Data(Sheet1).csv files are in the airtribe-hackathon directory (the same directory as app.py).

4. Grok (xAI) API Key Configuration
The application reads your xAI API key from the `XAI_API_KEY` environment variable. Get a key at https://console.x.ai. Without it, the dashboard still works for all built-in metrics (totals, refunds, payment method performance, etc.), but free-text AI answers will return a friendly message asking you to configure the key instead of crashing the server. You can optionally set `GROK_MODEL` (defaults to `grok-4`) to choose a different Grok model.

# On Windows (in Command Prompt):

set XAI_API_KEY=YOUR_XAI_API_KEY_HERE

# On macOS/Linux:

export XAI_API_KEY="YOUR_XAI_API_KEY_HERE"

## IMPORTANT: Replace YOUR_XAI_API_KEY_HERE with your actual key, then run app.py from the same shell.


5. Run the Flask Backend
With your virtual environment activated, run the Flask application:


#python app.py

The backend server will start, typically running on http://127.0.0.1:5000 (or http://localhost:5000). You should see output similar to * Running on http://127.0.0.1:5000 in your terminal.

6. Access the Frontend
Open your web browser and navigate to:


[http://127.0.0.1:5000/index.html](https://www.google.com/search?q=http://127.0.0.1:5000/index.html)

(Or simply http://localhost:5000/index.html if it redirects)

You will be presented with a login screen.

#Username: admin
#Password: admin
After successful login, the dashboard will become visible.

##💡 Usage Examples
Once logged in, type your questions into the input field and click "Ask." Here are some example prompts:

General Sales:

"How much did I receive in successful payments today?"
"What was my total revenue yesterday?"
"How much did I receive on 2025-01-20?" (Adjust date to match your data)
"What were the total sales for February 2025?" (Adjust month/year to match your data)
Refund Analysis:

"Why did my refunds spike yesterday?"
"Analyze the root cause of refunds on 2025-01-18." (Adjust date to match your data)
Payment Method Performance:

"Which payment method is performing best this week?"
"Show me the trend for UPI payments this month."
"Give me the transaction count for each payment method."
Customer Behavior:

"Analyze customer behavior for Credit Card payments."
"Tell me about repeat rates for mobile customers."
Recommendations & Forecasts:

"Should I enable EMI options?"
"What are the expected transactions for the upcoming weekend?"
System Alerts:

"Are there any alerts?"
"Check for any unusual transaction volume today."
⚠️ Troubleshooting
"Connection error" with AI / "Missing bearer authentication":

This indicates the Flask backend cannot reach api.x.ai.
Verify Internet Connectivity: Ensure the machine running Flask has internet access (e.g., by visiting https://www.google.com or https://api.x.ai/v1/models in a browser on that machine; if it gives a JSON error rather than a connection failure, connectivity is fine and the issue is the API key).
Firewall: Temporarily disable local firewalls (Windows Defender, macOS Firewall, ufw on Linux) for testing. If on a corporate network, contact IT to allow outbound HTTPS (port 443) traffic to api.x.ai.
Proxy: If you're behind a corporate proxy, you might need to set HTTP_PROXY and HTTPS_PROXY environment variables before running python app.py (e.g., export HTTPS_PROXY="http://your.proxy.server:port").
API Key: Make sure XAI_API_KEY is set as an environment variable in the same shell you run `python app.py` from.
"I currently only have transaction data from YYYY-MM-DD. I cannot provide insights for..."

This is not an error, but an informational message. Your loaded data (from CSVs or mock data) has a specific date range. Query only for dates that fall within or after 2025-01-15 for transaction data, and 2025-01-03 for refund data.
Charts not appearing:

Ensure the Flask backend is returning chartData in the correct JSON format (with labels, data, and type).
Check your browser's developer console for JavaScript errors.


#🔮 Future Enhancements

User Management: Implement a more robust user authentication system.

Custom Date Range Selection: Allow users to specify start and end dates directly in the UI.

More Data Sources: Integrate with live payment gateways or other financial APIs.

Advanced Analytics: Implement more sophisticated predictive models (e.g., churn prediction, lifetime value).

Dashboard Customization: Allow users to drag-and-drop widgets or customize their view.

Sentiment Analysis: Integrate support ticket data with sentiment analysis to identify urgent customer issues.

#📄 License

This project is open-source and available under the MIT License.
