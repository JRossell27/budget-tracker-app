import os
import streamlit as st
import pandas as pd
import datetime
import matplotlib.pyplot as plt
from git import Repo
import shutil

# === RENDER OPTIMIZATION ===
os.environ["STREAMLIT_SERVER_PORT"] = os.environ.get("PORT", "10000")
os.environ["STREAMLIT_SERVER_ADDRESS"] = "0.0.0.0"

# === SECRETS / ENV VARIABLES ===
if "GITHUB_REPO_URL" in st.secrets:
    GITHUB_REPO_URL = st.secrets["GITHUB_REPO_URL"]
    GITHUB_TOKEN = st.secrets["GITHUB_TOKEN"]
else:
    GITHUB_REPO_URL = os.environ.get("GITHUB_REPO_URL")
    GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")

DATA_FOLDER = "budget_data"
CATEGORY_FILE = "categories.csv"
RECURRING_FILE = "recurring.csv"
REPO_DIR = "budget_repo"
REMOTE_REPO = GITHUB_REPO_URL.replace("https://", f"https://{GITHUB_TOKEN}@")

# === GITHUB FUNCTIONS (OPTIMIZED) ===
def clone_or_pull_repo():
    """Clone repo if not exists; if exists, try pull, otherwise ignore errors."""
    if not os.path.exists(REPO_DIR):
        Repo.clone_from(REMOTE_REPO, REPO_DIR)
    else:
        try:
            repo = Repo(REPO_DIR)
            origin = repo.remotes.origin
            origin.pull()
        except:
            pass  # Ignore pull errors

    # Copy files from repo to working dir
    if os.path.exists(os.path.join(REPO_DIR, DATA_FOLDER)):
        os.makedirs(DATA_FOLDER, exist_ok=True)
        for file in os.listdir(os.path.join(REPO_DIR, DATA_FOLDER)):
            shutil.copy(os.path.join(REPO_DIR, DATA_FOLDER, file), DATA_FOLDER)
    for f in [CATEGORY_FILE, RECURRING_FILE]:
        if os.path.exists(os.path.join(REPO_DIR, f)):
            shutil.copy(os.path.join(REPO_DIR, f), f)

def push_changes_to_repo():
    """Push updated files back to GitHub, force pushing if needed."""
    repo = Repo(REPO_DIR)
    os.makedirs(os.path.join(REPO_DIR, DATA_FOLDER), exist_ok=True)

    for file in os.listdir(DATA_FOLDER):
        shutil.copy(os.path.join(DATA_FOLDER, file), os.path.join(REPO_DIR, DATA_FOLDER, file))
    for f in [CATEGORY_FILE, RECURRING_FILE]:
        if os.path.exists(f):
            shutil.copy(f, os.path.join(REPO_DIR, f))

    repo.git.add(A=True)
    try:
        repo.index.commit(f"Auto-update on {datetime.datetime.now().isoformat()}")
    except:
        pass

    try:
        repo.remotes.origin.push()
    except:
        repo.git.push("--force")

# === CATEGORY FUNCTIONS ===
def load_categories():
    if os.path.exists(CATEGORY_FILE):
        return pd.read_csv(CATEGORY_FILE)["category"].tolist()
    else:
        return []

def save_categories(categories):
    pd.DataFrame({"category": categories}).to_csv(CATEGORY_FILE, index=False)
    push_changes_to_repo()

# === RECURRING CHARGES FUNCTIONS ===
def load_recurring():
    if os.path.exists(RECURRING_FILE):
        return pd.read_csv(RECURRING_FILE)
    else:
        return pd.DataFrame(columns=["id", "type", "amount", "category", "note"])

def save_recurring(df: pd.DataFrame):
    df.to_csv(RECURRING_FILE, index=False)
    push_changes_to_repo()

def add_recurring(t_type, amount, category, note):
    df = load_recurring()
    new_id = int(df["id"].max() + 1) if not df.empty else 1
    new_row = pd.DataFrame([{"id": new_id, "type": t_type, "amount": amount, "category": category, "note": note}])
    df = pd.concat([df, new_row], ignore_index=True)
    save_recurring(df)

def delete_recurring(rid):
    df = load_recurring()
    df = df[df["id"] != rid]
    save_recurring(df)

def apply_recurring_to_month(year, month):
    rec_df = load_recurring()
    if rec_df.empty:
        return 0
    month_df = load_transactions(year, month)
    count = 0
    for _, row in rec_df.iterrows():
        new_id = generate_transaction_id(month_df)
        transaction = {
            "id": new_id,
            "date": datetime.date.today().isoformat(),
            "type": row["type"],
            "amount": row["amount"],
            "category": row["category"],
            "note": row["note"],
        }
        month_df = pd.concat([month_df, pd.DataFrame([transaction])], ignore_index=True)
        count += 1
    save_transactions(month_df, year, month)
    return count

# === TRANSACTION FUNCTIONS ===
def get_month_file(year: int, month: int) -> str:
    return os.path.join(DATA_FOLDER, f"{year}-{month:02d}.csv")

def load_transactions(year: int, month: int) -> pd.DataFrame:
    filename = get_month_file(year, month)
    if os.path.exists(filename):
        return pd.read_csv(filename)
    else:
        return pd.DataFrame(columns=["id", "date", "type", "amount", "category", "note"])

def load_all_transactions():
    all_data = []
    if not os.path.exists(DATA_FOLDER):
        return pd.DataFrame(columns=["id", "date", "type", "amount", "category", "note", "Year", "Month"])
    for file in os.listdir(DATA_FOLDER):
        if file.endswith(".csv"):
            df = pd.read_csv(os.path.join(DATA_FOLDER, file))
            if not df.empty:
                df["Year"] = int(file.split("-")[0])
                df["Month"] = int(file.split("-")[1].replace(".csv", ""))
                all_data.append(df)
    if all_data:
        return pd.concat(all_data, ignore_index=True)
    return pd.DataFrame(columns=["id", "date", "type", "amount", "category", "note", "Year", "Month"])

def save_transactions(df: pd.DataFrame, year: int, month: int):
    df.to_csv(get_month_file(year, month), index=False)
    push_changes_to_repo()

def save_transaction(transaction: dict, year: int, month: int):
    df = load_transactions(year, month)
    df = pd.concat([df, pd.DataFrame([transaction])], ignore_index=True)
    save_transactions(df, year, month)

def generate_transaction_id(df: pd.DataFrame) -> int:
    if df.empty:
        return 1
    return int(df["id"].max()) + 1

def calculate_totals(df: pd.DataFrame):
    if df.empty:
        return 0, 0, 0
    income = df[df["type"] == "income"]["amount"].sum()
    expenses = df[df["type"] == "expense"]["amount"].sum()
    return income, expenses, income - expenses

def category_tally(df: pd.DataFrame):
    if df.empty:
        return pd.DataFrame(columns=["Category", "Type", "Total"])
    tally = df.groupby(["category", "type"])["amount"].sum().reset_index()
    tally = tally.rename(columns={"category": "Category", "type": "Type", "amount": "Total"})
    tally = tally.sort_values(by=["Type", "Total"], ascending=[True, False])
    return tally

def top_categories(df: pd.DataFrame, n=3):
    if df.empty:
        return pd.DataFrame(columns=["Category", "Total"])
    top = (
        df[df["type"] == "expense"]
        .groupby("category")["amount"]
        .sum()
        .sort_values(ascending=False)
        .head(n)
        .reset_index()
    )
    top = top.rename(columns={"category": "Category", "amount": "Total"})
    return top

# === CHART FUNCTIONS ===
def show_pie_chart(df: pd.DataFrame):
    if df.empty or "expense" not in df["type"].values:
        st.info("No expenses to display.")
        return
    expense_data = df[df["type"] == "expense"].groupby("category")["amount"].sum()
    fig, ax = plt.subplots()
    ax.pie(expense_data, labels=expense_data.index, autopct="%1.1f%%", startangle=90)
    ax.set_title("Expense Breakdown by Category")
    st.pyplot(fig)

def show_income_vs_expense_chart(df: pd.DataFrame):
    income, expenses, _ = calculate_totals(df)
    fig, ax = plt.subplots()
    ax.bar(["Income", "Expenses"], [income, expenses], color=["green", "red"])
    ax.set_ylabel("Amount ($)")
    ax.set_title("Income vs Expenses")
    st.pyplot(fig)

def show_all_time_dashboard():
    all_df = load_all_transactions()
    if all_df.empty:
        st.info("No data available yet.")
        return
    st.subheader("📆 All-Time Summary")
    year_summary = []
    for year in sorted(all_df["Year"].unique()):
        df = all_df[all_df["Year"] == year]
        income, expenses, balance = calculate_totals(df)
        year_summary.append({"Year": year, "Income": income, "Expenses": expenses, "Balance": balance})
    summary_df = pd.DataFrame(year_summary)
    st.dataframe(summary_df)

    st.subheader("📈 Net Balance Over Time")
    monthly = all_df.groupby(["Year", "Month", "type"])["amount"].sum().reset_index()
    monthly_pivot = monthly.pivot_table(index=["Year", "Month"], columns="type", values="amount", fill_value=0)
    monthly_pivot["Net Balance"] = monthly_pivot.get("income", 0) - monthly_pivot.get("expense", 0)
    monthly_pivot = monthly_pivot.reset_index()
    fig, ax = plt.subplots()
    ax.plot(monthly_pivot.index, monthly_pivot["Net Balance"], marker="o", color="blue")
    ax.set_title("Net Balance Trend Over Time")
    ax.set_ylabel("Net Balance ($)")
    st.pyplot(fig)

    st.subheader("📊 Income vs Expenses by Month")
    fig, ax = plt.subplots()
    ax.bar(monthly_pivot.index, monthly_pivot.get("income", 0), color="green", label="Income")
    ax.bar(monthly_pivot.index, monthly_pivot.get("expense", 0), color="red", alpha=0.7, label="Expenses")
    ax.set_title("Monthly Income vs Expenses")
    ax.legend()
    st.pyplot(fig)

    st.subheader("🏆 Top Spending Categories (All Time)")
    top_df = (
        all_df[all_df["type"] == "expense"]
        .groupby("category")["amount"]
        .sum()
        .sort_values(ascending=False)
        .head(5)
        .reset_index()
    )
    st.table(top_df)

# === INIT: SYNC WITH GITHUB ON STARTUP ===
clone_or_pull_repo()

# === STREAMLIT APP ===
st.set_page_config(page_title="Budget Tracker v3.4 (Render Optimized)", layout="wide")
st.title("💰 Pro Budget Tracker v3.4 (Render Optimized)")

tabs = st.tabs(["📊 Dashboard", "✏️ Manage Transactions", "📆 All-Time Dashboard", "⚙️ Settings"])

# === DASHBOARD TAB ===
with tabs[0]:
    current_year = datetime.date.today().year
    current_month = datetime.date.today().month
    years = list(range(current_year - 5, current_year + 1))
    months = list(range(1, 13))

    col1, col2 = st.columns(2)
    with col1:
        selected_year = st.selectbox("Select Year", reversed(years), index=0)
    with col2:
        selected_month = st.selectbox("Select Month", months, index=current_month - 1)

    df = load_transactions(selected_year, selected_month)
    categories = load_categories()

    income, expenses, balance = calculate_totals(df)
    st.subheader(f"📊 {selected_year}-{selected_month:02d} Summary")
    col1, col2, col3 = st.columns(3)
    col1.metric("Income", f"${income:,.2f}")
    col2.metric("Expenses", f"${expenses:,.2f}")
    col3.metric("Balance", f"${balance:,.2f}")

    if st.button("🔁 Apply Recurring Charges to This Month"):
        count = apply_recurring_to_month(selected_year, selected_month)
        st.success(f"✅ {count} recurring charges added!")
        st.rerun()

    st.subheader("🏆 Top Spending Categories (This Month)")
    top_df = top_categories(df, n=3)
    if top_df.empty:
        st.info("No expenses this month yet.")
    else:
        st.table(top_df)

    with st.expander("📌 Running Tally by Category"):
        tally_df = category_tally(df)
        if tally_df.empty:
            st.info("No transactions yet.")
        else:
            st.dataframe(tally_df)

    st.subheader("➕ Add a Transaction")
    with st.form("add_transaction_form"):
        t_type = st.selectbox("Type", ["income", "expense"])
        amount = st.number_input("Amount", min_value=0.01, step=0.01)
        category = st.selectbox("Category", options=categories + ["Other"])
        custom_category = ""
        if category == "Other":
            custom_category = st.text_input("New Category Name")
        note = st.text_input("Note (optional)")
        submitted = st.form_submit_button("Add Transaction")

        if submitted:
            if category == "Other":
                category = custom_category.strip()
                if category and category not in categories:
                    categories.append(category)
                    save_categories(categories)
            if amount > 0 and category:
                new_id = generate_transaction_id(df)
                new_transaction = {
                    "id": new_id,
                    "date": datetime.date.today().isoformat(),
                    "type": t_type,
                    "amount": amount,
                    "category": category,
                    "note": note,
                }
                save_transaction(new_transaction, selected_year, selected_month)
                st.success(f"✅ {t_type.capitalize()} of ${amount:.2f} added!")
                st.rerun()
            else:
                st.error("Please enter a valid amount and category.")

    with st.expander("📜 Transactions Table"):
        if df.empty:
            st.info("No transactions yet.")
        else:
            st.dataframe(df, use_container_width=True)

    with st.expander("📈 Visualizations"):
        chart_type = st.radio("Choose Chart", ["Pie Chart (Expenses)", "Income vs Expenses"])
        if chart_type == "Pie Chart (Expenses)":
            show_pie_chart(df)
        else:
            show_income_vs_expense_chart(df)

# === MANAGE TRANSACTIONS TAB ===
with tabs[1]:
    selected_year = st.selectbox("Select Year", reversed(years), index=0, key="manage_year")
    selected_month = st.selectbox("Select Month", months, index=current_month - 1, key="manage_month")
    df = load_transactions(selected_year, selected_month)

    if df.empty:
        st.info("No transactions to manage.")
    else:
        st.subheader(f"✏️ Edit or Delete Transactions ({selected_year}-{selected_month:02d})")
        st.dataframe(df)
        transaction_options = [
            f"ID {row.id} | {row.date} | {row.type} | ${row.amount} | {row.category}"
            for _, row in df.iterrows()
        ]
        selected_option = st.selectbox("Select a transaction", ["None"] + transaction_options)

        if selected_option != "None":
            selected_id = int(selected_option.split(" ")[1])
            transaction = df[df["id"] == selected_id].iloc[0]

            new_amount = st.number_input("New Amount", value=float(transaction["amount"]))
            new_category = st.text_input("New Category", value=transaction["category"])
            new_note = st.text_input("New Note", value=transaction["note"])

            col1, col2 = st.columns(2)
            with col1:
                if st.button("Save Changes"):
                    df.loc[df["id"] == selected_id, ["amount", "category", "note"]] = [
                        new_amount,
                        new_category,
                        new_note,
                    ]
                    save_transactions(df, selected_year, selected_month)
                    st.success(f"✅ Transaction {selected_id} updated.")
                    st.rerun()
            with col2:
                if st.button("Delete Transaction"):
                    df = df[df["id"] != selected_id]
                    save_transactions(df, selected_year, selected_month)
                    st.success(f"✅ Transaction {selected_id} deleted.")
                    st.rerun()

# === ALL-TIME DASHBOARD TAB ===
with tabs[2]:
    show_all_time_dashboard()

# === SETTINGS TAB ===
with tabs[3]:
    st.subheader("⚙️ Manage Categories")
    categories = load_categories()
    st.write("Current Categories:", categories)
    new_category = st.text_input("Add New Category")
    if st.button("Add Category"):
        if new_category and new_category not in categories:
            categories.append(new_category)
            save_categories(categories)
            st.success(f"✅ Category '{new_category}' added.")
            st.rerun()
    delete_category = st.selectbox("Delete a Category", ["None"] + categories)
    if st.button("Delete Category") and delete_category != "None":
        categories = [c for c in categories if c != delete_category]
        save_categories(categories)
        st.success(f"✅ Category '{delete_category}' deleted.")
        st.rerun()

    st.subheader("🔁 Manage Recurring Charges")
    rec_df = load_recurring()
    if not rec_df.empty:
        st.table(rec_df)
    r_type = st.selectbox("Type", ["income", "expense"])
    r_amount = st.number_input("Amount", min_value=0.01, step=0.01)
    r_category = st.text_input("Category")
    r_note = st.text_input("Note (optional)")
    if st.button("Add Recurring Charge"):
        if r_category and r_amount > 0:
            add_recurring(r_type, r_amount, r_category, r_note)
            st.success(f"✅ Recurring {r_type} added.")
            st.rerun()
    r_delete = st.selectbox(
        "Delete a Recurring Charge",
        ["None"] + [f"ID {rid}" for rid in rec_df["id"]] if not rec_df.empty else ["None"],
    )
    if st.button("Delete Recurring Charge") and r_delete != "None":
        rid = int(r_delete.split(" ")[1])
        delete_recurring(rid)
        st.success(f"✅ Recurring charge {rid} deleted.")
        st.rerun()
