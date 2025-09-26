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

def add_recurring(t_type, amount, category, note):
    df = load_recurring()
    new_id = int(df["id"].max() + 1) if not df.empty else 1
    df = pd.concat([df, pd.DataFrame([{"id": new_id, "type": t_type, "amount": amount, "category": category, "note": note, "source": ""}])], ignore_index=True)
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
    fig, ax = plt.subplots()
    ax.pie(data, labels=data.index, autopct="%1.1f%%", startangle=90)
    ax.set_title("Expense Breakdown by Category")
    st.pyplot(fig)

def show_income_vs_expense_chart(df):
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
    summary = [{"Year": y, **dict(zip(["Income", "Expenses", "Balance"], calculate_totals(all_df[all_df["Year"] == y])))} for y in sorted(all_df["Year"].unique())]
    st.dataframe(pd.DataFrame(summary))
    st.subheader("📈 Net Balance Over Time")
    monthly = all_df.groupby(["Year", "Month", "type"])["amount"].sum().reset_index().pivot_table(index=["Year", "Month"], columns="type", values="amount", fill_value=0)
    monthly["Net Balance"] = monthly.get("income", 0) - monthly.get("expense", 0)
    monthly = monthly.reset_index()
    fig, ax = plt.subplots()
    ax.plot(monthly.index, monthly["Net Balance"], marker="o", color="blue")
    st.pyplot(fig)
    st.subheader("🏆 Top Spending Categories (All Time)")
    st.table(all_df[all_df["type"] == "expense"].groupby("category")["amount"].sum().sort_values(ascending=False).head(5).reset_index())
    st.subheader("📦 Category Totals — All Time")
    all_category_totals = category_tally(all_df)
    if all_category_totals.empty:
        st.info("No category totals available yet.")
    else:
        st.table(all_category_totals)

# === INIT ===
clone_or_pull_repo()

# === STREAMLIT APP (MOBILE FRIENDLY + DARK MODE + LAST SYNC) ===
st.set_page_config(page_title="Budget Tracker v3.6.1", layout="wide")
st.title("💰 Budget Tracker v3.6.1 (Mobile + Dark Mode)")

tabs = st.tabs(["📊 Dashboard", "✏️ Transactions", "📆 All-Time", "🗓️ Past Months", "⚙️ Settings"])

# === DASHBOARD TAB ===
with tabs[0]:
    # Show last synced status
    if os.path.exists("last_synced.txt"):
        with open("last_synced.txt", "r") as f:
            last_synced = f.read().strip()
    else:
        last_synced = "Not yet synced"
    st.caption(f"✅ **Last Synced:** {last_synced}")

    current_year, current_month = datetime.date.today().year, datetime.date.today().month
    years, months = list(range(current_year - 5, current_year + 1)), list(range(1, 13))
    selected_year, selected_month = st.selectbox("Year", reversed(years)), st.selectbox("Month", months, index=current_month - 1)
    df = load_transactions(selected_year, selected_month)

    income, expenses, balance = calculate_totals(df)
    st.markdown(f"""
    <div style="padding:8px; border-radius:8px; border:1px solid rgba(255,255,255,0.2);">
    <b>Income:</b> ${income:,.2f} | <b>Expenses:</b> ${expenses:,.2f} | <b>Balance:</b> ${balance:,.2f}
    </div>
    """, unsafe_allow_html=True)

    if st.button("🔁 Apply Recurring Charges"):
        st.success(f"✅ {apply_recurring_to_month(selected_year, selected_month)} recurring charges added!")
        st.rerun()

    st.subheader("🏆 Top Spending Categories")
    st.table(top_categories(df, 3))

    st.subheader("📈 Visualizations")
    chart_choice = st.radio("Choose Chart", ["Pie Chart (Expenses)", "Income vs Expenses"], horizontal=True)
    if chart_choice == "Pie Chart (Expenses)":
        show_pie_chart(df)
    else:
        show_income_vs_expense_chart(df)

# === TRANSACTIONS TAB ===
with tabs[1]:
    selected_year, selected_month = st.selectbox("Year", reversed(years), key="y2"), st.selectbox("Month", months, index=current_month - 1, key="m2")
    df = load_transactions(selected_year, selected_month)
    categories = load_categories()
    sources = load_sources()
    if "add_txn_type" not in st.session_state:
        st.session_state["add_txn_type"] = "expense"
    if "add_txn_source" not in st.session_state:
        st.session_state["add_txn_source"] = sources[0] if sources else ""

    type_options = ["income", "expense"]
    default_type = st.session_state.get("add_txn_type", type_options[0])
    type_index = type_options.index(default_type) if default_type in type_options else 0

    source_options = sources.copy()
    if "Other" not in source_options:
        source_options.append("Other")
    default_source = st.session_state.get("add_txn_source", source_options[0] if source_options else "Other")
    if default_source and default_source not in source_options:
        source_options.insert(0, default_source)
    source_index = source_options.index(default_source) if default_source in source_options else 0

    st.subheader("➕ Add Transaction")
    with st.form("add_txn_transactions", clear_on_submit=True):
        t_type = st.radio("Type", type_options, horizontal=True, index=type_index)
        amount = st.number_input("Amount", min_value=0.01, step=0.01)
        category = st.selectbox("Category", categories + ["Other"])
        custom_category = st.text_input("New Category") if category == "Other" else ""
        note = st.text_input("Note (optional)")
        source_choice = st.selectbox("Source", source_options, index=source_index)
        custom_source = st.text_input("New Source", key="add_new_source") if source_choice == "Other" else ""
        default_date = st.session_state.get("add_txn_date", datetime.date.today())
        txn_date = st.date_input("Date", value=default_date, key="add_txn_date")
        if st.form_submit_button("Add"):
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

    if df.empty:
        st.info("No transactions.")
    else:
        st.dataframe(df)
        opt = st.selectbox("Select", ["None"] + [f"ID {r.id} | {r.type} ${r.amount}" for _, r in df.iterrows()])
        if opt != "None":
            tid = int(opt.split()[1])
            row = df[df["id"] == tid].iloc[0]
            new_amt = st.number_input("Amount", value=float(row["amount"]))
            new_cat = st.text_input("Category", row["category"])
            new_note = st.text_input("Note", row["note"])
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
            edit_custom_source = st.text_input("New Source", key=f"edit_new_source_{tid}") if new_source_choice == "Other" else ""

            if st.button("Save"):
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

                df.loc[df["id"] == tid, ["amount", "category", "note", "date", "source"]] = [
                    new_amt,
                    new_cat,
                    new_note,
                    edit_date.isoformat() if isinstance(edit_date, datetime.date) else datetime.date.today().isoformat(),
                    final_source
                ]
                save_transactions(df, selected_year, selected_month)
                st.success("✅ Updated!")
                st.rerun()

            if st.button("Delete"):
                save_transactions(df[df["id"] != tid], selected_year, selected_month)
                st.success("✅ Deleted!")
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
        st.dataframe(monthly_summary[["Month Label", "Income", "Expenses", "Balance"]].set_index("Month Label"))

        month_options = monthly_summary["Month Label"].tolist()
        selected_label = st.selectbox("Select a month", month_options)
        selected_year, selected_month = map(int, selected_label.split("-"))
        selected_row = monthly_summary[monthly_summary["Month Label"] == selected_label].iloc[0]

        c1, c2, c3 = st.columns(3)
        c1.metric("Income", f"${selected_row['Income']:,.2f}")
        c2.metric("Expenses", f"${selected_row['Expenses']:,.2f}")
        c3.metric("Balance", f"${selected_row['Balance']:,.2f}")

        st.markdown(f"**Transactions for {selected_label}**")
        month_df = load_transactions(selected_year, selected_month)
        if month_df.empty:
            st.info("No transactions recorded for this month.")
        else:
            st.subheader(f"📂 Category Totals — {selected_label}")
            month_category_totals = category_tally(month_df)
            if month_category_totals.empty:
                st.info("No category totals to display for this month.")
            else:
                st.table(month_category_totals)
            st.dataframe(month_df)

# === SETTINGS TAB ===
with tabs[4]:
    st.subheader("Categories")
    cats = load_categories()
    st.write("Current:", cats)
    nc = st.text_input("Add Category")
    if st.button("Add") and nc and nc not in cats:
        cats.append(nc)
        save_categories(cats)
        st.success("✅ Added!")
        st.rerun()
    dc = st.selectbox("Delete", ["None"] + cats)
    if st.button("Delete") and dc != "None":
        save_categories([c for c in cats if c != dc])
        st.success("✅ Deleted!")
        st.rerun()

    st.subheader("Sources")
    srcs = load_sources()
    st.write("Current:", srcs)
    ns = st.text_input("Add Source", key="settings_add_source")
    if st.button("Add Source") and ns and ns not in srcs:
        srcs.append(ns)
        save_sources(srcs)
        st.success("✅ Added!")
        st.rerun()
    ds = st.selectbox("Delete Source", ["None"] + srcs, key="settings_delete_source")
    if st.button("Delete Source") and ds != "None":
        save_sources([s for s in srcs if s != ds])
        st.success("✅ Deleted!")
        st.rerun()

    st.subheader("Recurring Charges")
    rec_df = load_recurring()
    if not rec_df.empty:
        st.table(rec_df)
    rt = st.radio("Type", ["income", "expense"], horizontal=True)
    ra = st.number_input("Amount", min_value=0.01, step=0.01)
    rc = st.text_input("Category")
    rn = st.text_input("Note")
    if st.button("Add Recurring"):
        add_recurring(rt, ra, rc, rn)
        st.success("✅ Added!")
        st.rerun()
    dr = st.selectbox("Delete Recurring", ["None"] + [f"ID {r}" for r in rec_df["id"]]) if not rec_df.empty else "None"
    if st.button("Delete Recurring") and dr != "None":
        delete_recurring(int(dr.split()[1]))
        st.success("✅ Deleted!")
        st.rerun()
