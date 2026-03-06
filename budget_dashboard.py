import os
import streamlit as st
import pandas as pd
import datetime
import matplotlib.pyplot as plt
from git import Repo
import shutil

# === RENDER/STREAMLIT CLOUD OPTIMIZATION ===
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
SOURCE_FILE = "sources.csv"
REPO_DIR = "budget_repo"
REMOTE_REPO = GITHUB_REPO_URL.replace("https://", f"https://{GITHUB_TOKEN}@")

# === GITHUB FUNCTIONS (FORCE FRESH SYNC + TIMESTAMP) ===
def clone_or_pull_repo():
    """Always ensure we have the freshest data from GitHub and record last sync time."""
    if not os.path.exists(REPO_DIR) or not os.path.exists(os.path.join(REPO_DIR, ".git")):
        if os.path.exists(REPO_DIR):
            shutil.rmtree(REPO_DIR)
        Repo.clone_from(REMOTE_REPO, REPO_DIR)
    else:
        try:
            repo = Repo(REPO_DIR)
            repo.remotes.origin.pull()
        except:
            shutil.rmtree(REPO_DIR)
            Repo.clone_from(REMOTE_REPO, REPO_DIR)

    # Always copy the latest data into budget_data
    if os.path.exists(os.path.join(REPO_DIR, DATA_FOLDER)):
        os.makedirs(DATA_FOLDER, exist_ok=True)
        for file in os.listdir(os.path.join(REPO_DIR, DATA_FOLDER)):
            shutil.copy(os.path.join(REPO_DIR, DATA_FOLDER, file), DATA_FOLDER)

    for f in [CATEGORY_FILE, RECURRING_FILE, SOURCE_FILE]:
        if os.path.exists(os.path.join(REPO_DIR, f)):
            shutil.copy(os.path.join(REPO_DIR, f), f)

    # Save last synced timestamp
    with open("last_synced.txt", "w") as f:
        f.write(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

def push_changes_to_repo():
    if not os.path.exists(REPO_DIR) or not os.path.exists(os.path.join(REPO_DIR, ".git")):
        if os.path.exists(REPO_DIR):
            shutil.rmtree(REPO_DIR)
        Repo.clone_from(REMOTE_REPO, REPO_DIR)
    repo = Repo(REPO_DIR)
    os.makedirs(os.path.join(REPO_DIR, DATA_FOLDER), exist_ok=True)
    for file in os.listdir(DATA_FOLDER):
        shutil.copy(os.path.join(DATA_FOLDER, file), os.path.join(REPO_DIR, DATA_FOLDER, file))
    for f in [CATEGORY_FILE, RECURRING_FILE, SOURCE_FILE]:
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

# === CATEGORY & RECURRING ===
def load_categories():
    return pd.read_csv(CATEGORY_FILE)["category"].tolist() if os.path.exists(CATEGORY_FILE) else []

def save_categories(categories):
    pd.DataFrame({"category": categories}).to_csv(CATEGORY_FILE, index=False)
    push_changes_to_repo()

def load_sources():
    return pd.read_csv(SOURCE_FILE)["source"].tolist() if os.path.exists(SOURCE_FILE) else []

def save_sources(sources):
    pd.DataFrame({"source": sources}).to_csv(SOURCE_FILE, index=False)
    push_changes_to_repo()

def load_recurring():
    if os.path.exists(RECURRING_FILE):
        df = pd.read_csv(RECURRING_FILE)
        if "source" not in df.columns:
            df["source"] = ""
        return df
    return pd.DataFrame(columns=["id", "type", "amount", "category", "note", "source"])

def save_recurring(df):
    df.to_csv(RECURRING_FILE, index=False)
    push_changes_to_repo()

def add_recurring(t_type, amount, category, note, source=""):
    df = load_recurring()
    new_id = int(df["id"].max() + 1) if not df.empty else 1
    df = pd.concat([df, pd.DataFrame([{"id": new_id, "type": t_type, "amount": amount, "category": category, "note": note, "source": source}])], ignore_index=True)
    save_recurring(df)

def delete_recurring(rid):
    df = load_recurring()
    save_recurring(df[df["id"] != rid])

def apply_recurring_to_month(year, month):
    rec_df = load_recurring()
    if rec_df.empty:
        return 0
    df = load_transactions(year, month)
    count = 0
    for _, row in rec_df.iterrows():
        source_value = row.get("source", "")
        if pd.isna(source_value) or not str(source_value).strip():
            source_value = "Recurring"
        df = pd.concat([df, pd.DataFrame([{
            "id": generate_transaction_id(df),
            "date": datetime.date.today().isoformat(),
            "type": row["type"],
            "amount": row["amount"],
            "category": row["category"],
            "note": row["note"],
            "source": source_value
        }])], ignore_index=True)
        count += 1
    save_transactions(df, year, month)
    return count

# === TRANSACTIONS ===
def get_month_file(year, month):
    return os.path.join(DATA_FOLDER, f"{year}-{month:02d}.csv")

def load_transactions(year, month):
    required_cols = ["id", "date", "type", "amount", "category", "note", "source"]
    if os.path.exists(get_month_file(year, month)):
        df = pd.read_csv(get_month_file(year, month))
        for col in required_cols:
            if col not in df.columns:
                df[col] = "" if col in {"date", "type", "category", "note", "source"} else 0
        df["id"] = pd.to_numeric(df["id"], errors="coerce").fillna(0).astype(int)
        df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0.0)
        return df[required_cols]
    return pd.DataFrame(columns=required_cols)

def load_all_transactions():
    if not os.path.exists(DATA_FOLDER):
        return pd.DataFrame(columns=["id", "date", "type", "amount", "category", "note", "source", "Year", "Month"])
    all_data = []
    for file in os.listdir(DATA_FOLDER):
        if file.endswith(".csv"):
            df = pd.read_csv(os.path.join(DATA_FOLDER, file))
            if not df.empty:
                for col in ["source"]:
                    if col not in df.columns:
                        df[col] = ""
                df["id"] = pd.to_numeric(df["id"], errors="coerce").fillna(0).astype(int)
                df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0.0)
                df["Year"], df["Month"] = int(file[:4]), int(file[5:7])
                all_data.append(df)
    return pd.concat(all_data, ignore_index=True) if all_data else pd.DataFrame(columns=["id", "date", "type", "amount", "category", "note", "source", "Year", "Month"])

def save_transactions(df, year, month):
    df.to_csv(get_month_file(year, month), index=False)
    push_changes_to_repo()

def save_transaction(transaction, year, month):
    df = load_transactions(year, month)
    df = pd.concat([df, pd.DataFrame([transaction])], ignore_index=True)
    save_transactions(df, year, month)

def generate_transaction_id(df):
    return 1 if df.empty else int(df["id"].max()) + 1

def calculate_totals(df):
    if df.empty:
        return 0, 0, 0
    income = df[df["type"] == "income"]["amount"].sum()
    expenses = df[df["type"] == "expense"]["amount"].sum()
    return income, expenses, income - expenses

def category_tally(df):
    return (df.groupby(["category", "type"])["amount"].sum().reset_index()
              .rename(columns={"category": "Category", "type": "Type", "amount": "Total"})
              .sort_values(by=["Type", "Total"], ascending=[True, False])) if not df.empty else pd.DataFrame(columns=["Category", "Type", "Total"])

def top_categories(df, n=3):
    return (df[df["type"] == "expense"].groupby("category")["amount"].sum()
              .sort_values(ascending=False).head(n).reset_index()
              .rename(columns={"category": "Category", "amount": "Total"})) if not df.empty else pd.DataFrame(columns=["Category", "Total"])

# === CHARTS ===
def show_pie_chart(df):
    if df.empty or "expense" not in df["type"].values:
        st.info("No expenses to display.")
        return
    data = df[df["type"] == "expense"].groupby("category")["amount"].sum()
    fig, ax = plt.subplots(figsize=(7, 5))
    wedges, texts, autotexts = ax.pie(
        data, labels=data.index, autopct="%1.1f%%", startangle=90,
        colors=plt.cm.Set3.colors[:len(data)]
    )
    for text in autotexts:
        text.set_fontsize(9)
    ax.set_title("Expense Breakdown by Category", fontsize=13, fontweight="bold")
    st.pyplot(fig)
    plt.close(fig)

def show_income_vs_expense_chart(df):
    income, expenses, _ = calculate_totals(df)
    fig, ax = plt.subplots(figsize=(5, 4))
    bars = ax.bar(["Income", "Expenses"], [income, expenses], color=["#2ecc71", "#e74c3c"], width=0.5)
    ax.set_ylabel("Amount ($)")
    ax.set_title("Income vs Expenses", fontsize=13, fontweight="bold")
    top = max(income, expenses)
    for bar, val in zip(bars, [income, expenses]):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + top * 0.01,
                f"${val:,.2f}", ha="center", va="bottom", fontweight="bold", fontsize=10)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"${x:,.0f}"))
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    st.pyplot(fig)
    plt.close(fig)

def show_all_time_dashboard():
    all_df = load_all_transactions()
    if all_df.empty:
        st.info("No data available yet.")
        return

    st.subheader("📆 Yearly Summary")
    summary = []
    for y in sorted(all_df["Year"].unique()):
        inc, exp, bal = calculate_totals(all_df[all_df["Year"] == y])
        summary.append({"Year": y, "Income": inc, "Expenses": exp, "Balance": bal})
    summary_df = pd.DataFrame(summary)
    st.dataframe(
        summary_df.style.format({"Income": "${:,.2f}", "Expenses": "${:,.2f}", "Balance": "${:,.2f}"}),
        use_container_width=True, hide_index=True
    )

    st.subheader("📈 Net Balance Over Time")
    monthly = (all_df.groupby(["Year", "Month", "type"])["amount"].sum()
               .reset_index()
               .pivot_table(index=["Year", "Month"], columns="type", values="amount", fill_value=0))
    monthly["Net Balance"] = monthly.get("income", 0) - monthly.get("expense", 0)
    monthly = monthly.reset_index()
    monthly["Label"] = monthly.apply(lambda r: f"{int(r['Year'])}-{int(r['Month']):02d}", axis=1)
    x_vals = list(range(len(monthly)))
    net = monthly["Net Balance"].tolist()
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(x_vals, net, marker="o", color="#3498db", linewidth=2)
    ax.axhline(0, color="gray", linestyle="--", linewidth=0.8)
    ax.fill_between(x_vals, net, 0,
                    where=[v >= 0 for v in net], alpha=0.15, color="green", label="Positive")
    ax.fill_between(x_vals, net, 0,
                    where=[v < 0 for v in net], alpha=0.15, color="red", label="Negative")
    ax.set_xticks(x_vals)
    ax.set_xticklabels(monthly["Label"].tolist(), rotation=45, ha="right")
    ax.set_ylabel("Net Balance ($)")
    ax.set_title("Monthly Net Balance Trend", fontsize=13, fontweight="bold")
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"${x:,.0f}"))
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    plt.tight_layout()
    st.pyplot(fig)
    plt.close(fig)

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("🏆 Top Spending Categories (All Time)")
        top5 = (all_df[all_df["type"] == "expense"]
                .groupby("category")["amount"].sum()
                .sort_values(ascending=False).head(5).reset_index()
                .rename(columns={"category": "Category", "amount": "Total"}))
        st.dataframe(
            top5.style.format({"Total": "${:,.2f}"}),
            use_container_width=True, hide_index=True
        )
    with col2:
        st.subheader("📦 Category Totals — All Time")
        all_category_totals = category_tally(all_df)
        if all_category_totals.empty:
            st.info("No category totals available yet.")
        else:
            st.dataframe(
                all_category_totals.style.format({"Total": "${:,.2f}"}),
                use_container_width=True, hide_index=True
            )

# === INIT ===
clone_or_pull_repo()

# === PAGE CONFIG ===
st.set_page_config(page_title="Budget Tracker", page_icon="💰", layout="wide")

MONTH_NAMES = ["January", "February", "March", "April", "May", "June",
               "July", "August", "September", "October", "November", "December"]

current_year = datetime.date.today().year
current_month = datetime.date.today().month
years = list(range(current_year - 5, current_year + 1))

# === SIDEBAR: Global Period Selector + Sync Status ===
with st.sidebar:
    st.title("💰 Budget Tracker")

    if os.path.exists("last_synced.txt"):
        with open("last_synced.txt", "r") as f:
            last_synced = f.read().strip()
    else:
        last_synced = "Not yet synced"
    st.caption(f"✅ Last synced: {last_synced}")

    st.divider()
    st.subheader("📅 Selected Period")
    selected_year = st.selectbox("Year", list(reversed(years)), key="global_year")
    selected_month = st.selectbox(
        "Month",
        list(range(1, 13)),
        format_func=lambda m: MONTH_NAMES[m - 1],
        index=current_month - 1,
        key="global_month"
    )

# === MAIN HEADER ===
st.title(f"💰 {MONTH_NAMES[selected_month - 1]} {selected_year}")

tabs = st.tabs(["📊 Dashboard", "✏️ Transactions", "📆 All-Time", "🗓️ Past Months", "⚙️ Settings"])

# === DASHBOARD TAB ===
with tabs[0]:
    df = load_transactions(selected_year, selected_month)
    income, expenses, balance = calculate_totals(df)
    savings_rate = (balance / income * 100) if income > 0 else 0.0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("💰 Income", f"${income:,.2f}")
    col2.metric("💸 Expenses", f"${expenses:,.2f}")
    col3.metric("📊 Balance", f"${balance:,.2f}", delta=round(balance, 2))
    col4.metric("📈 Savings Rate", f"{savings_rate:.1f}%", delta=round(savings_rate, 1))

    st.divider()

    if st.button("🔁 Apply Recurring Charges"):
        count = apply_recurring_to_month(selected_year, selected_month)
        st.success(f"✅ {count} recurring charges applied to {MONTH_NAMES[selected_month - 1]} {selected_year}!")
        st.rerun()

    col_left, col_right = st.columns([1, 1])
    with col_left:
        st.subheader("🏆 Top Spending Categories")
        top = top_categories(df, 5)
        if top.empty:
            st.info("No expenses this month yet.")
        else:
            st.dataframe(top.style.format({"Total": "${:,.2f}"}), use_container_width=True, hide_index=True)
    with col_right:
        st.subheader("📈 Visualization")
        chart_choice = st.radio("Chart Type", ["Pie Chart (Expenses)", "Income vs Expenses"], horizontal=True)
        if chart_choice == "Pie Chart (Expenses)":
            show_pie_chart(df)
        else:
            show_income_vs_expense_chart(df)

# === TRANSACTIONS TAB ===
with tabs[1]:
    df = load_transactions(selected_year, selected_month)
    categories = load_categories()
    sources = load_sources()

    if "add_txn_type" not in st.session_state:
        st.session_state["add_txn_type"] = "expense"
    if "add_txn_source" not in st.session_state:
        st.session_state["add_txn_source"] = sources[0] if sources else ""

    type_options = ["income", "expense"]
    default_type = st.session_state.get("add_txn_type", "expense")
    type_index = type_options.index(default_type) if default_type in type_options else 0

    source_options = sources.copy()
    if "Other" not in source_options:
        source_options.append("Other")
    default_source = st.session_state.get("add_txn_source", source_options[0] if source_options else "Other")
    if default_source and default_source not in source_options:
        source_options.insert(0, default_source)
    source_index = source_options.index(default_source) if default_source in source_options else 0

    col_form, col_table = st.columns([1, 2])

    with col_form:
        st.subheader("➕ Add Transaction")
        with st.form("add_txn_transactions", clear_on_submit=True):
            t_type = st.radio("Type", type_options, horizontal=True, index=type_index)
            amount = st.number_input("Amount ($)", min_value=0.01, step=0.01)
            category = st.selectbox("Category", categories + ["Other"])
            custom_category = st.text_input("New Category Name") if category == "Other" else ""
            note = st.text_input("Note (optional)")
            source_choice = st.selectbox("Source", source_options, index=source_index)
            custom_source = st.text_input("New Source Name", key="add_new_source") if source_choice == "Other" else ""
            default_date = st.session_state.get("add_txn_date", datetime.date.today())
            txn_date = st.date_input("Date", value=default_date, key="add_txn_date")
            if st.form_submit_button("Add Transaction", type="primary", use_container_width=True):
                if category == "Other":
                    category = custom_category.strip()
                    if category and category not in categories:
                        categories.append(category)
                        save_categories(categories)
                if source_choice == "Other":
                    source_choice = custom_source.strip()
                    if source_choice and source_choice not in sources:
                        sources.append(source_choice)
                        save_sources(sources)
                if not category:
                    st.warning("Please provide a category.")
                elif not source_choice:
                    st.warning("Please provide a source.")
                else:
                    st.session_state["add_txn_type"] = t_type
                    st.session_state["add_txn_source"] = source_choice
                    transaction_date = txn_date.isoformat() if isinstance(txn_date, datetime.date) else datetime.date.today().isoformat()
                    save_transaction({
                        "id": generate_transaction_id(df),
                        "date": transaction_date,
                        "type": t_type,
                        "amount": amount,
                        "category": category,
                        "note": note,
                        "source": source_choice
                    }, selected_year, selected_month)
                    st.success("✅ Transaction added!")
                    st.rerun()

    with col_table:
        st.subheader(f"📋 Transactions — {MONTH_NAMES[selected_month - 1]} {selected_year}")
        if df.empty:
            st.info("No transactions recorded for this month.")
        else:
            display_df = df.copy().sort_values("date", ascending=False)
            display_df["amount"] = display_df["amount"].apply(lambda x: f"${x:,.2f}")
            display_df.columns = ["ID", "Date", "Type", "Amount", "Category", "Note", "Source"]
            st.dataframe(display_df, use_container_width=True, hide_index=True)
            csv_data = df.to_csv(index=False)
            st.download_button(
                "⬇️ Download CSV",
                csv_data,
                f"{selected_year}-{selected_month:02d}.csv",
                "text/csv"
            )

    if not df.empty:
        st.divider()
        st.subheader("✏️ Edit or Delete a Transaction")
        opt = st.selectbox(
            "Select transaction",
            ["— Select —"] + [f"ID {r.id} | {r.date} | {r.type} | ${r.amount:,.2f} | {r.category}" for _, r in df.iterrows()],
            key="edit_select"
        )
        if opt != "— Select —":
            tid = int(opt.split()[1])
            row = df[df["id"] == tid].iloc[0]

            col_e1, col_e2 = st.columns(2)
            with col_e1:
                type_edit_options = ["income", "expense"]
                current_type_idx = type_edit_options.index(row["type"]) if row["type"] in type_edit_options else 0
                new_type = st.radio("Type", type_edit_options, horizontal=True, index=current_type_idx, key=f"edit_type_{tid}")
                new_amt = st.number_input("Amount ($)", value=float(row["amount"]), key=f"edit_amt_{tid}")
                new_cat = st.text_input("Category", row["category"], key=f"edit_cat_{tid}")
                new_note = st.text_input("Note", row["note"] if row["note"] else "", key=f"edit_note_{tid}")
            with col_e2:
                try:
                    existing_date = datetime.date.fromisoformat(str(row["date"])) if row["date"] else datetime.date.today()
                except ValueError:
                    existing_date = datetime.date.today()
                edit_date = st.date_input("Date", value=existing_date, key=f"edit_date_{tid}")

                source_edit_options = sources.copy()
                current_source = row.get("source", "")
                if current_source and current_source not in source_edit_options:
                    source_edit_options.append(current_source)
                if "Other" not in source_edit_options:
                    source_edit_options.append("Other")
                source_index_edit = source_edit_options.index(current_source) if current_source in source_edit_options else 0
                new_source_choice = st.selectbox("Source", source_edit_options, index=source_index_edit, key=f"edit_source_{tid}")
                edit_custom_source = st.text_input("New Source Name", key=f"edit_new_source_{tid}") if new_source_choice == "Other" else ""

            col_save, col_delete = st.columns(2)
            with col_save:
                if st.button("💾 Save Changes", use_container_width=True, type="primary"):
                    if new_source_choice == "Other":
                        new_source_value = edit_custom_source.strip()
                        if not new_source_value:
                            st.warning("Please provide a source before saving.")
                            st.stop()
                        if new_source_value not in sources:
                            sources.append(new_source_value)
                            save_sources(sources)
                        final_source = new_source_value
                    else:
                        final_source = new_source_choice

                    df.loc[df["id"] == tid, ["type", "amount", "category", "note", "date", "source"]] = [
                        new_type,
                        new_amt,
                        new_cat,
                        new_note,
                        edit_date.isoformat() if isinstance(edit_date, datetime.date) else datetime.date.today().isoformat(),
                        final_source
                    ]
                    save_transactions(df, selected_year, selected_month)
                    st.success("✅ Transaction updated!")
                    st.rerun()
            with col_delete:
                if st.button("🗑️ Delete Transaction", use_container_width=True):
                    save_transactions(df[df["id"] != tid], selected_year, selected_month)
                    st.success("✅ Transaction deleted!")
                    st.rerun()

# === ALL-TIME TAB ===
with tabs[2]:
    show_all_time_dashboard()

# === PAST MONTHS TAB ===
with tabs[3]:
    st.subheader("🗓️ Monthly History")
    all_df = load_all_transactions()
    if all_df.empty:
        st.info("No historical data yet.")
    else:
        monthly_summary = (all_df.groupby(["Year", "Month", "type"])["amount"].sum()
                              .reset_index()
                              .pivot_table(index=["Year", "Month"], columns="type", values="amount", fill_value=0)
                              .reset_index())
        if "income" not in monthly_summary.columns:
            monthly_summary["income"] = 0.0
        if "expense" not in monthly_summary.columns:
            monthly_summary["expense"] = 0.0
        monthly_summary = monthly_summary.rename(columns={"income": "Income", "expense": "Expenses"})
        monthly_summary["Balance"] = monthly_summary["Income"] - monthly_summary["Expenses"]
        monthly_summary = monthly_summary.sort_values(by=["Year", "Month"], ascending=[False, False])
        monthly_summary["Month Label"] = monthly_summary.apply(lambda row: f"{int(row['Year'])}-{int(row['Month']):02d}", axis=1)

        st.markdown("**Monthly Totals**")
        st.dataframe(
            monthly_summary[["Month Label", "Income", "Expenses", "Balance"]]
            .set_index("Month Label")
            .style.format({"Income": "${:,.2f}", "Expenses": "${:,.2f}", "Balance": "${:,.2f}"}),
            use_container_width=True
        )

        month_options = monthly_summary["Month Label"].tolist()
        selected_label = st.selectbox("Select a month to view details", month_options)
        sel_year, sel_month = map(int, selected_label.split("-"))
        selected_row = monthly_summary[monthly_summary["Month Label"] == selected_label].iloc[0]

        c1, c2, c3 = st.columns(3)
        c1.metric("💰 Income", f"${selected_row['Income']:,.2f}")
        c2.metric("💸 Expenses", f"${selected_row['Expenses']:,.2f}")
        c3.metric("📊 Balance", f"${selected_row['Balance']:,.2f}", delta=round(selected_row['Balance'], 2))

        month_df = load_transactions(sel_year, sel_month)
        if month_df.empty:
            st.info("No transactions recorded for this month.")
        else:
            st.subheader(f"📂 Category Totals — {selected_label}")
            month_category_totals = category_tally(month_df)
            if not month_category_totals.empty:
                st.dataframe(
                    month_category_totals.style.format({"Total": "${:,.2f}"}),
                    use_container_width=True, hide_index=True
                )
            st.subheader(f"📋 Transactions — {selected_label}")
            display_month_df = month_df.copy().sort_values("date", ascending=False)
            display_month_df["amount"] = display_month_df["amount"].apply(lambda x: f"${x:,.2f}")
            display_month_df.columns = ["ID", "Date", "Type", "Amount", "Category", "Note", "Source"]
            st.dataframe(display_month_df, use_container_width=True, hide_index=True)

# === SETTINGS TAB ===
with tabs[4]:
    with st.expander("📂 Categories", expanded=True):
        cats = load_categories()
        st.write("**Current:**", ", ".join(cats) if cats else "None")
        col_a, col_b = st.columns(2)
        with col_a:
            nc = st.text_input("New Category Name", key="settings_add_cat")
            if st.button("Add Category", key="btn_add_cat") and nc and nc not in cats:
                cats.append(nc)
                save_categories(cats)
                st.success(f"✅ '{nc}' added!")
                st.rerun()
        with col_b:
            dc = st.selectbox("Remove Category", ["— Select —"] + cats, key="settings_del_cat")
            if st.button("Delete Category", key="btn_del_cat") and dc != "— Select —":
                save_categories([c for c in cats if c != dc])
                st.success(f"✅ '{dc}' removed!")
                st.rerun()

    with st.expander("🏦 Sources", expanded=True):
        srcs = load_sources()
        st.write("**Current:**", ", ".join(srcs) if srcs else "None")
        col_a, col_b = st.columns(2)
        with col_a:
            ns = st.text_input("New Source Name", key="settings_add_source")
            if st.button("Add Source", key="btn_add_src") and ns and ns not in srcs:
                srcs.append(ns)
                save_sources(srcs)
                st.success(f"✅ '{ns}' added!")
                st.rerun()
        with col_b:
            ds = st.selectbox("Remove Source", ["— Select —"] + srcs, key="settings_delete_source")
            if st.button("Delete Source", key="btn_del_src") and ds != "— Select —":
                save_sources([s for s in srcs if s != ds])
                st.success(f"✅ '{ds}' removed!")
                st.rerun()

    with st.expander("🔁 Recurring Charges", expanded=True):
        rec_df = load_recurring()
        if not rec_df.empty:
            st.dataframe(rec_df.style.format({"amount": "${:,.2f}"}), use_container_width=True, hide_index=True)
        else:
            st.info("No recurring charges configured.")

        st.markdown("**Add Recurring Charge**")
        col_r1, col_r2 = st.columns(2)
        with col_r1:
            rt = st.radio("Type", ["income", "expense"], horizontal=True, key="rec_type")
            ra = st.number_input("Amount ($)", min_value=0.01, step=0.01, key="rec_amount")
            rc = st.text_input("Category", key="rec_cat")
        with col_r2:
            rn = st.text_input("Note", key="rec_note")
            rec_source_opts = load_sources() + ["Recurring", "Other"]
            rs = st.selectbox("Source", rec_source_opts, key="rec_source")
            if rs == "Other":
                rs = st.text_input("Custom Source", key="rec_custom_source")
        if st.button("Add Recurring Charge", key="btn_add_rec"):
            add_recurring(rt, ra, rc, rn, rs)
            st.success("✅ Recurring charge added!")
            st.rerun()

        if not rec_df.empty:
            st.markdown("**Remove Recurring Charge**")
            dr_options = ["— Select —"] + [
                f"ID {r['id']} — {r['category']} ${r['amount']:,.2f}"
                for _, r in rec_df.iterrows()
            ]
            dr = st.selectbox("Select to delete", dr_options, key="rec_del_select")
            if st.button("Delete Recurring", key="btn_del_rec") and dr != "— Select —":
                delete_recurring(int(dr.split()[1]))
                st.success("✅ Deleted!")
                st.rerun()
