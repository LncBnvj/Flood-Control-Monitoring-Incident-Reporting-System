# flood_control_mysql_gui.py
import customtkinter as ctk
from tkinter import ttk, messagebox, filedialog
import mysql.connector
from mysql.connector import errorcode
import csv
from datetime import datetime
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# -----------------------
# CONFIG: set DB credentials
# -----------------------
DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "",   # <-- change this
    "port": 3307, 
    "database": "flood_control"       # DB name used by default
}

# -----------------------
# HELPER: connect to MySQL (optionally create DB/tables)
# -----------------------
def get_connection(create_if_missing=True):
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        return conn
    except mysql.connector.Error as err:
        # If DB doesn't exist, optionally create it
        if create_if_missing and err.errno == errorcode.ER_BAD_DB_ERROR:
            try:
                tmp = mysql.connector.connect(host=DB_CONFIG["host"],
                                              user=DB_CONFIG["user"],
                                              password=DB_CONFIG["password"])
                cursor = tmp.cursor()
                cursor.execute(f"CREATE DATABASE IF NOT EXISTS {DB_CONFIG['database']} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
                tmp.commit() if hasattr(tmp, "commit") else None
                cursor.close()
                tmp.close()
                # try again
                conn = mysql.connector.connect(**DB_CONFIG)
                return conn
            except Exception as e:
                raise
        else:
            raise

# -----------------------
# SCHEMA CREATION & SEED (idempotent)
# -----------------------
def ensure_schema_and_seed():
    conn = get_connection(create_if_missing=True)
    cur = conn.cursor()
    # create tables
    cur.execute("""
    CREATE TABLE IF NOT EXISTS areas (
      id INT AUTO_INCREMENT PRIMARY KEY,
      name VARCHAR(200) NOT NULL,
      province VARCHAR(150) NOT NULL,
      risk_level ENUM('High','Medium','Low') NOT NULL DEFAULT 'Medium',
      population_affected INT UNSIGNED DEFAULT 0,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      UNIQUE KEY ux_area_name_province (name, province)
    ) ENGINE=InnoDB;
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS projects (
      id INT AUTO_INCREMENT PRIMARY KEY,
      project_name VARCHAR(255) NOT NULL,
      area_id INT NOT NULL,
      start_date DATE DEFAULT NULL,
      end_date DATE DEFAULT NULL,
      status ENUM('Ongoing','Delayed','Completed') DEFAULT 'Ongoing',
      remarks TEXT,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY (area_id) REFERENCES areas(id) ON DELETE RESTRICT ON UPDATE CASCADE,
      INDEX idx_projects_area (area_id)
    ) ENGINE=InnoDB;
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS incidents (
      id INT AUTO_INCREMENT PRIMARY KEY,
      area_id INT NOT NULL,
      date DATE NOT NULL,
      flood_level DECIMAL(5,2) DEFAULT 0.00,
      damage_estimate DECIMAL(14,2) DEFAULT 0.00,
      casualties INT UNSIGNED DEFAULT 0,
      notes TEXT,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY (area_id) REFERENCES areas(id) ON DELETE RESTRICT ON UPDATE CASCADE,
      INDEX idx_incidents_area (area_id),
      INDEX idx_incidents_date (date)
    ) ENGINE=InnoDB;
    """)
    conn.commit()

    # seed minimal sample data only if areas is empty
    cur.execute("SELECT COUNT(*) FROM areas")
    if cur.fetchone()[0] == 0:
        sample_areas = [
            ("Manila", "Metro Manila", "High", 1500000),
            ("Cebu City", "Cebu", "Medium", 900000),
            ("Davao City", "Davao del Sur", "Low", 700000),
            ("Quezon City", "Metro Manila", "High", 2000000),
            ("Iloilo City", "Iloilo", "Medium", 800000)
        ]
        cur.executemany("INSERT INTO areas (name,province,risk_level,population_affected) VALUES (%s,%s,%s,%s)", sample_areas)
        conn.commit()

    # seed projects if empty
    cur.execute("SELECT COUNT(*) FROM projects")
    if cur.fetchone()[0] == 0:
        # map area names to ids
        cur.execute("SELECT id,name FROM areas")
        areas_map = {name: id_ for (id_, name) in cur.fetchall()}
        sample_projects = [
            ("Drainage Improvement", areas_map.get("Manila"), "2025-01-01", "2025-06-30", "Ongoing", "Delayed funding"),
            ("Flood Gate Construction", areas_map.get("Cebu City"), "2025-02-01", "2025-07-15", "Delayed", "Controversial contractor"),
            ("River Dredging", areas_map.get("Davao City"), "2025-03-01", "2025-08-30", "Ongoing", "Insufficient manpower")
        ]
        cur.executemany("INSERT INTO projects (project_name,area_id,start_date,end_date,status,remarks) VALUES (%s,%s,%s,%s,%s,%s)",
                        sample_projects)
        conn.commit()

    # seed incidents if empty
    cur.execute("SELECT COUNT(*) FROM incidents")
    if cur.fetchone()[0] == 0:
        cur.execute("SELECT id,name FROM areas")
        areas_map = {name: id_ for (id_, name) in cur.fetchall()}
        sample_incidents = [
            (areas_map.get("Manila"), "2025-04-12", 3.50, 5000000, 5, "Severe flooding, poor drainage"),
            (areas_map.get("Cebu City"), "2025-03-20", 2.00, 2000000, 1, "Medium flooding, ignored warnings"),
            (areas_map.get("Davao City"), "2025-05-05", 1.20, 1000000, 0, "Minimal flooding, timely evacuation")
        ]
        cur.executemany("INSERT INTO incidents (area_id,date,flood_level,damage_estimate,casualties,notes) VALUES (%s,%s,%s,%s,%s,%s)",
                        sample_incidents)
        conn.commit()

    cur.close()
    conn.close()

# Ensure DB and seed data exist
try:
    ensure_schema_and_seed()
except Exception as e:
    messagebox.showerror("DB Error", f"Error creating DB/schema: {e}")
    raise

# -----------------------
# UI: CustomTkinter App
# -----------------------
ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

app = ctk.CTk()
app.title("Flood Control Manager (MySQL)")
app.geometry("1400x900")

# ============================
# COLLAPSIBLE SIDEBAR SETTINGS
# ============================

sidebar_width = 220
sidebar_expanded = True

def toggle_sidebar():
    """Expand or collapse the sidebar."""
    global sidebar_expanded
    if sidebar_expanded:
        sidebar_frame.grid_remove()
        sidebar_toggle_btn.configure(text="☰")
    else:
        sidebar_frame.grid()
        sidebar_toggle_btn.configure(text="≡ Menu")
    sidebar_expanded = not sidebar_expanded


# ============================
# MAIN LAYOUT STRUCTURE
# ============================

main_container = ctk.CTkFrame(app)
main_container.pack(fill="both", expand=True)

# Grid for sidebar + content
main_container.grid_columnconfigure(0, weight=0)   # Sidebar
main_container.grid_columnconfigure(1, weight=1)   # Main content
main_container.grid_rowconfigure(0, weight=1)


# ============================
# SIDEBAR
# ============================

sidebar_frame = ctk.CTkFrame(main_container, width=sidebar_width, corner_radius=0)
sidebar_frame.grid(row=0, column=0, sticky="ns")
sidebar_frame.grid_propagate(False)

# Sidebar buttons
def go_to_tab(tab_name):
    tabview.set(tab_name)

ctk.CTkLabel(sidebar_frame, text="📁", font=("Arial", 18, "bold")).pack(pady=(15, 10))

ctk.CTkButton(sidebar_frame, text="📊 Dashboard", command=lambda: go_to_tab("Dashboard")).pack(fill="x", padx=10, pady=5)
ctk.CTkButton(sidebar_frame, text="📍 Areas", command=lambda: go_to_tab("Areas")).pack(fill="x", padx=10, pady=5)
ctk.CTkButton(sidebar_frame, text="🏗 Projects", command=lambda: go_to_tab("Projects")).pack(fill="x", padx=10, pady=5)
ctk.CTkButton(sidebar_frame, text="⚠ Incidents", command=lambda: go_to_tab("Incidents")).pack(fill="x", padx=10, pady=5)
ctk.CTkButton(sidebar_frame, text="📝 Reports", command=lambda: go_to_tab("Reports")).pack(fill="x", padx=10, pady=5)
ctk.CTkLabel(sidebar_frame, text="Version 1.0", text_color="gray").pack(side="bottom", pady=10)

# ============================
# SIDEBAR TOGGLE BUTTON
# ============================

# Using absolute placement to avoid overlap
sidebar_toggle_btn = ctk.CTkButton(
    app,
    text="≡ Menu",
    width=80,
    corner_radius=6,
    command=toggle_sidebar
)
sidebar_toggle_btn.place(x=10, y=10)  # Top-left overlay button

# Create tabview
tabview = ctk.CTkTabview(main_container, width=1300)
tabview.grid(row=0, column=1, sticky="nsew", padx=12, pady=12)

tabview.add("Dashboard")
tabview.add("Areas")
tabview.add("Projects")
tabview.add("Incidents")
tabview.add("Reports")

# ----- Utility: run a SELECT and return rows -----
def fetch_rows(sql, params=None):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(sql, params or ())
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows

# ============================
# DASHBOARD TAB
# ============================

dashboard_tab = tabview.tab("Dashboard")

dash_container = ctk.CTkFrame(dashboard_tab)
dash_container.pack(fill="both", expand=True, padx=20, pady=20)
dash_container.grid_columnconfigure((0,1,2,3), weight=1)
dash_container.grid_rowconfigure(0, weight=1)

REFRESH_INTERVAL = 5000  # milliseconds (5000 ms = 5 seconds)

def refresh_dashboard():

    # ---- Fetch Current KPIs ----
    total_areas = fetch_rows("SELECT COUNT(*) FROM areas")[0][0]
    total_projects = fetch_rows("SELECT COUNT(*) FROM projects")[0][0]
    total_incidents = fetch_rows("SELECT COUNT(*) FROM incidents")[0][0]
    high_risk = fetch_rows("SELECT COUNT(*) FROM areas WHERE risk_level='High'")[0][0]

    # ---- Fetch KPIs since 2025-12-01 for automatic summary ----
    date_cutoff = "2025-01-01"

    areas_after_date = fetch_rows(f"SELECT COUNT(*) FROM areas WHERE created_at <= '{date_cutoff}'")[0][0]
    projects_after_date = fetch_rows(f"SELECT COUNT(*) FROM projects WHERE created_at <= '{date_cutoff}'")[0][0]
    incidents_after_date = fetch_rows(f"SELECT COUNT(*) FROM incidents WHERE created_at <= '{date_cutoff}'")[0][0]
    high_risk_after_date = fetch_rows(f"SELECT COUNT(*) FROM areas WHERE risk_level='High' AND created_at <= '{date_cutoff}'")[0][0]

    # ---- Function to calculate summary and color ----
    def calculate_summary_and_color(current, after_date, positive_is_good=True):
        change = current - after_date
        if change > 0:
            summary = f"+{change} since {date_cutoff}"
            color = "#4CAF50" if positive_is_good else "#F44336"  # green if good, red if bad
        elif change < 0:
            summary = f"{change} since {date_cutoff}"
            color = "#F44336" if positive_is_good else "#4CAF50"  # red if bad, green if improvement
        else:
            summary = "No change"
            color = "#9E9E9E"
        return summary, color

    # ---- KPI Cards ----
    def create_stat_card(parent, label, value, summary, color, col):
        card = ctk.CTkFrame(parent, corner_radius=12, fg_color=color)
        card.grid(row=0, column=col, sticky="nsew", padx=10, pady=10)

        card.grid_propagate(False)
        card.configure(height=120, width=200)

        # Center container
        center_frame = ctk.CTkFrame(card, fg_color="transparent")
        center_frame.place(relx=0.5, rely=0.5, anchor="center")  # PERFECT CENTER

        ctk.CTkLabel(center_frame, text=label, font=("Arial", 16, "bold"), text_color="white").pack(pady=2)
        ctk.CTkLabel(center_frame, text=str(value), font=("Arial", 30, "bold"), text_color="white").pack(pady=2)
        ctk.CTkLabel(center_frame, text=summary, font=("Arial", 11), text_color="white").pack(pady=2)

    # Generate summaries and colors
    summary_areas, color_areas = calculate_summary_and_color(total_areas, areas_after_date)
    summary_projects, color_projects = calculate_summary_and_color(total_projects, projects_after_date)
    summary_incidents, color_incidents = calculate_summary_and_color(total_incidents, incidents_after_date, positive_is_good=False)
    summary_high_risk, color_high_risk = calculate_summary_and_color(high_risk, high_risk_after_date, positive_is_good=False)

    # Create KPI cards
    create_stat_card(dash_container, "Total Areas", total_areas, summary_areas, color_areas, 0)
    create_stat_card(dash_container, "Total Projects", total_projects, summary_projects, color_projects, 1)
    create_stat_card(dash_container, "Total Incidents", total_incidents, summary_incidents, color_incidents, 2)
    create_stat_card(dash_container, "High Risk Areas", high_risk, summary_high_risk, color_high_risk, 3)

# ============================
# FLOOD LEVEL BAR CHART (FIXED)
# ============================

global chart_frame

# Remove previous chart frame to avoid duplication
try:
    chart_frame.destroy()
except:
    pass

chart_frame = ctk.CTkFrame(dashboard_tab)
chart_frame.pack(fill="both", expand=True, padx=20, pady=10)

inc_data = fetch_rows("""
    SELECT a.name, AVG(i.flood_level)
    FROM incidents i 
    JOIN areas a ON i.area_id = a.id
    GROUP BY a.name
""")

if inc_data:
    areas = [row[0] for row in inc_data]
    avg_levels = [float(row[1]) for row in inc_data]

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(areas, avg_levels, color="#3b8ed0")
    ax.set_title("Average Flood Level per Area")
    ax.set_ylabel("Flood Level (meters)")
    ax.set_xticklabels(areas, rotation=30, ha="right")

    chart_canvas = FigureCanvasTkAgg(fig, master=chart_frame)
    chart_canvas.get_tk_widget().pack(fill="both", expand=True)
    chart_canvas.draw()

dashboard_tab.after(REFRESH_INTERVAL, refresh_dashboard)

# Start auto-refresh
refresh_dashboard()

# -----------------------
# AREAS TAB (form top, table middle, buttons bottom)
# -----------------------
areas_tab = tabview.tab("Areas")

# form (top row) - horizontal
area_form = ctk.CTkFrame(areas_tab)
area_form.grid(row=0, column=0, sticky="ew", padx=8, pady=(8,4))
area_form.grid_columnconfigure((0,1,2,3,4,5,6,7), weight=1)

area_name = ctk.CTkEntry(area_form, placeholder_text="Area Name")
province = ctk.CTkEntry(area_form, placeholder_text="Province")
risk = ctk.CTkComboBox(area_form, values=["High","Medium","Low"])
population = ctk.CTkEntry(area_form, placeholder_text="Population Affected")

ctk.CTkLabel(area_form, text="Area Name").grid(row=0,column=0, sticky="w", padx=4)
area_name.grid(row=0,column=1, sticky="ew", padx=4)
ctk.CTkLabel(area_form, text="Province").grid(row=0,column=2, sticky="w", padx=4)
province.grid(row=0,column=3, sticky="ew", padx=4)
ctk.CTkLabel(area_form, text="Risk").grid(row=0,column=4, sticky="w", padx=4)
risk.grid(row=0,column=5, sticky="ew", padx=4)
ctk.CTkLabel(area_form, text="Population").grid(row=0,column=6, sticky="w", padx=4)
population.grid(row=0,column=7, sticky="ew", padx=4)

# treeview (middle)
area_table_frame = ctk.CTkFrame(areas_tab)
area_table_frame.grid(row=1, column=0, sticky="nsew", padx=8, pady=4)
areas_tab.grid_rowconfigure(1, weight=1); areas_tab.grid_columnconfigure(0, weight=1)

area_tree = ttk.Treeview(area_table_frame, columns=("id","name","province","risk","population"), show="headings")
for col, w in (("id",60),("name",250),("province",180),("risk",100),("population",140)):
    area_tree.heading(col, text=col.title())
    area_tree.column(col, width=w, anchor="center")
area_tree.pack(fill="both", expand=True, padx=4, pady=4)

# buttons (bottom)
area_btn_frame = ctk.CTkFrame(areas_tab)
area_btn_frame.grid(row=2, column=0, sticky="ew", padx=8, pady=(4,8))
area_btn_frame.grid_columnconfigure((0,1,2,3), weight=1)

def refresh_area_table():
    for r in area_tree.get_children(): area_tree.delete(r)
    rows = fetch_rows("SELECT id,name,province,risk_level,population_affected FROM areas ORDER BY id ASC")
    for row in rows:
        area_tree.insert("", "end", values=row)
    # refresh combos in other tabs
    refresh_area_comboboxes()

def area_add():
    if not area_name.get() or not province.get():
        messagebox.showwarning("Missing", "Fill Area name and Province")
        return
    conn = get_connection(); cur = conn.cursor()
    cur.execute("INSERT INTO areas (name,province,risk_level,population_affected) VALUES (%s,%s,%s,%s)",
                (area_name.get(), province.get(), risk.get() or "Medium", population.get() or 0))
    conn.commit(); cur.close(); conn.close()
    refresh_area_table()

def area_update():
    sel = area_tree.focus()
    if not sel: messagebox.showwarning("Select", "Choose an area"); return
    vals = area_tree.item(sel)["values"]
    aid = vals[0]
    conn = get_connection(); cur = conn.cursor()
    cur.execute("UPDATE areas SET name=%s, province=%s, risk_level=%s, population_affected=%s WHERE id=%s",
                (area_name.get(), province.get(), risk.get() or "Medium", population.get() or 0, aid))
    conn.commit(); cur.close(); conn.close()
    refresh_area_table()

def area_delete():
    sel = area_tree.focus()
    if not sel: messagebox.showwarning("Select", "Choose an area"); return
    vals = area_tree.item(sel)["values"]
    aid = vals[0]
    if not messagebox.askyesno("Confirm", f"Delete area ID {aid}? This will block if projects/incidents reference it."):
        return
    conn = get_connection(); cur = conn.cursor()
    try:
        cur.execute("DELETE FROM areas WHERE id=%s", (aid,))
        conn.commit()
    except mysql.connector.IntegrityError:
        messagebox.showerror("Integrity", "Area is referenced by projects or incidents. Delete dependent rows first.")
    finally:
        cur.close(); conn.close()
    refresh_area_table()

def area_on_select(event):
    sel = area_tree.focus()
    if not sel: return
    vals = area_tree.item(sel)["values"]
    area_name.delete(0,"end"); area_name.insert(0, vals[1])
    province.delete(0,"end"); province.insert(0, vals[2])
    risk.set(vals[3])
    population.delete(0,"end"); population.insert(0, vals[4])

ctk.CTkButton(area_btn_frame, text="Add", fg_color="#2ecc71", command=area_add).grid(row=0,column=0, padx=6, pady=6)
ctk.CTkButton(area_btn_frame, text="Update", fg_color="#f1c40f", command=area_update).grid(row=0,column=1, padx=6, pady=6)
ctk.CTkButton(area_btn_frame, text="Delete", fg_color="#e74c3c", command=area_delete).grid(row=0,column=2, padx=6, pady=6)
ctk.CTkButton(area_btn_frame, text="Export CSV", fg_color="#3498db", command=lambda: export_tree_to_csv(area_tree, "areas_export.csv")).grid(row=0,column=3, padx=6, pady=6)

area_tree.bind("<<TreeviewSelect>>", area_on_select)

# -----------------------
# PROJECTS TAB
# -----------------------
projects_tab = tabview.tab("Projects")
proj_form = ctk.CTkFrame(projects_tab)
proj_form.grid(row=0, column=0, sticky="ew", padx=8, pady=(8,4))
projects_tab.grid_rowconfigure(1, weight=1); projects_tab.grid_columnconfigure(0, weight=1)
proj_form.grid_columnconfigure(tuple(range(12)), weight=1)

proj_name = ctk.CTkEntry(proj_form, placeholder_text="Project Name")
proj_area = ctk.CTkComboBox(proj_form, values=[])
proj_start = ctk.CTkEntry(proj_form, placeholder_text="Start YYYY-MM-DD")
proj_end = ctk.CTkEntry(proj_form, placeholder_text="End YYYY-MM-DD")
proj_status = ctk.CTkComboBox(proj_form, values=["Ongoing","Delayed","Completed"])
proj_remarks = ctk.CTkEntry(proj_form, placeholder_text="Remarks")

ctk.CTkLabel(proj_form, text="Name").grid(row=0,column=0, sticky="w", padx=4)
proj_name.grid(row=0,column=1, sticky="ew", padx=4)
ctk.CTkLabel(proj_form, text="Area").grid(row=0,column=2, sticky="w", padx=4)
proj_area.grid(row=0,column=3, sticky="ew", padx=4)
ctk.CTkLabel(proj_form, text="Start").grid(row=0,column=4, sticky="w", padx=4)
proj_start.grid(row=0,column=5, sticky="ew", padx=4)
ctk.CTkLabel(proj_form, text="End").grid(row=0,column=6, sticky="w", padx=4)
proj_end.grid(row=0,column=7, sticky="ew", padx=4)
ctk.CTkLabel(proj_form, text="Status").grid(row=0,column=8, sticky="w", padx=4)
proj_status.grid(row=0,column=9, sticky="ew", padx=4)
ctk.CTkLabel(proj_form, text="Remarks").grid(row=0,column=10, sticky="w", padx=4)
proj_remarks.grid(row=0,column=11, sticky="ew", padx=4)

proj_table_frame = ctk.CTkFrame(projects_tab)
proj_table_frame.grid(row=1, column=0, sticky="nsew", padx=8, pady=4)
proj_tree = ttk.Treeview(proj_table_frame, columns=("id","name","area","start","end","status","remarks"), show="headings")
for col,w in (("id",60),("name",300),("area",200),("start",100),("end",100),("status",100),("remarks",200)):
    proj_tree.heading(col, text=col.title()); proj_tree.column(col, width=w, anchor="center")
proj_tree.pack(fill="both", expand=True, padx=4, pady=4)

proj_btn_frame = ctk.CTkFrame(projects_tab)
proj_btn_frame.grid(row=2, column=0, sticky="ew", padx=8, pady=(4,8))
proj_btn_frame.grid_columnconfigure((0,1,2,3), weight=1)

def refresh_proj_table():
    for r in proj_tree.get_children(): proj_tree.delete(r)
    rows = fetch_rows("""SELECT p.id, p.project_name, a.name, p.start_date, p.end_date, p.status, p.remarks
                        FROM projects p JOIN areas a ON p.area_id=a.id ORDER BY p.created_at DESC""")
    for row in rows: proj_tree.insert("", "end", values=row)

def proj_add():
    if not proj_name.get() or not proj_area.get():
        messagebox.showwarning("Missing", "Project name and Area are required")
        return
    area_id = int(proj_area.get().split("ID:")[-1].replace(")",""))
    conn = get_connection(); cur = conn.cursor()
    cur.execute("INSERT INTO projects (project_name,area_id,start_date,end_date,status,remarks) VALUES (%s,%s,%s,%s,%s,%s)",
                (proj_name.get(), area_id, proj_start.get() or None, proj_end.get() or None, proj_status.get() or "Ongoing", proj_remarks.get()))
    conn.commit(); cur.close(); conn.close()
    refresh_proj_table()

def proj_update():
    sel = proj_tree.focus()
    if not sel: messagebox.showwarning("Select", "Pick a project"); return
    pid = proj_tree.item(sel)["values"][0]
    area_id = int(proj_area.get().split("ID:")[-1].replace(")",""))
    conn = get_connection(); cur = conn.cursor()
    cur.execute("UPDATE projects SET project_name=%s, area_id=%s, start_date=%s, end_date=%s, status=%s, remarks=%s WHERE id=%s",
                (proj_name.get(), area_id, proj_start.get() or None, proj_end.get() or None, proj_status.get() or "Ongoing", proj_remarks.get(), pid))
    conn.commit(); cur.close(); conn.close()
    refresh_proj_table()

def proj_delete():
    sel = proj_tree.focus()
    if not sel: return
    pid = proj_tree.item(sel)["values"][0]
    if not messagebox.askyesno("Confirm", f"Delete project {pid}?"): return
    conn = get_connection(); cur = conn.cursor()
    cur.execute("DELETE FROM projects WHERE id=%s", (pid,))
    conn.commit(); cur.close(); conn.close()
    refresh_proj_table()

def proj_on_select(event):
    sel = proj_tree.focus()
    if not sel: return
    vals = proj_tree.item(sel)["values"]
    proj_name.delete(0,"end"); proj_name.insert(0, vals[1])
    proj_area.set(f"{vals[2]} (ID:{vals[0]})" if vals[2] else "")
    proj_start.delete(0,"end"); proj_start.insert(0, vals[3] or "")
    proj_end.delete(0,"end"); proj_end.insert(0, vals[4] or "")
    proj_status.set(vals[5] or "")
    proj_remarks.delete(0,"end"); proj_remarks.insert(0, vals[6] or "")

ctk.CTkButton(proj_btn_frame, text="Add", fg_color="#2ecc71", command=proj_add).grid(row=0,column=0, padx=8, pady=6)
ctk.CTkButton(proj_btn_frame, text="Update", fg_color="#f1c40f", command=proj_update).grid(row=0,column=1, padx=8, pady=6)
ctk.CTkButton(proj_btn_frame, text="Delete", fg_color="#e74c3c", command=proj_delete).grid(row=0,column=2, padx=8, pady=6)
ctk.CTkButton(proj_btn_frame, text="Export CSV", fg_color="#3498db",
               command=lambda: export_tree_to_csv(proj_tree, "projects_export.csv")).grid(row=0,column=3, padx=8, pady=6)

proj_tree.bind("<<TreeviewSelect>>", proj_on_select)

# -----------------------
# INCIDENTS TAB
# -----------------------
inc_tab = tabview.tab("Incidents")
inc_form = ctk.CTkFrame(inc_tab)
inc_form.grid(row=0, column=0, sticky="ew", padx=8, pady=(8,4))
inc_tab.grid_rowconfigure(1, weight=1); inc_tab.grid_columnconfigure(0, weight=1)
inc_form.grid_columnconfigure(tuple(range(12)), weight=1)

inc_area = ctk.CTkComboBox(inc_form, values=[])
inc_date = ctk.CTkEntry(inc_form, placeholder_text="YYYY-MM-DD")
inc_level = ctk.CTkEntry(inc_form, placeholder_text="Flood level (m)")
inc_damage = ctk.CTkEntry(inc_form, placeholder_text="Damage (PHP)")
inc_casualties = ctk.CTkEntry(inc_form, placeholder_text="Casualties")
inc_notes = ctk.CTkEntry(inc_form, placeholder_text="Notes")

ctk.CTkLabel(inc_form, text="Area").grid(row=0,column=0, sticky="w", padx=4)
inc_area.grid(row=0,column=1, sticky="ew", padx=4)
ctk.CTkLabel(inc_form, text="Date").grid(row=0,column=2, sticky="w", padx=4)
inc_date.grid(row=0,column=3, sticky="ew", padx=4)
ctk.CTkLabel(inc_form, text="Level(m)").grid(row=0,column=4, sticky="w", padx=4)
inc_level.grid(row=0,column=5, sticky="ew", padx=4)
ctk.CTkLabel(inc_form, text="Damage").grid(row=0,column=6, sticky="w", padx=4)
inc_damage.grid(row=0,column=7, sticky="ew", padx=4)
ctk.CTkLabel(inc_form, text="Casualties").grid(row=0,column=8, sticky="w", padx=4)
inc_casualties.grid(row=0,column=9, sticky="ew", padx=4)
ctk.CTkLabel(inc_form, text="Notes").grid(row=0,column=10, sticky="w", padx=4)
inc_notes.grid(row=0,column=11, sticky="ew", padx=4)

inc_table_frame = ctk.CTkFrame(inc_tab)
inc_table_frame.grid(row=1, column=0, sticky="nsew", padx=8, pady=4)
inc_tree = ttk.Treeview(inc_table_frame, columns=("id","area","date","level","damage","casualties","notes"), show="headings")
for col,w in (("id",60),("area",220),("date",100),("level",100),("damage",150),("casualties",100),("notes",250)):
    inc_tree.heading(col, text=col.title()); inc_tree.column(col, width=w, anchor="center")
inc_tree.pack(fill="both", expand=True, padx=4, pady=4)

inc_btn_frame = ctk.CTkFrame(inc_tab)
inc_btn_frame.grid(row=2, column=0, sticky="ew", padx=8, pady=(4,8))
inc_btn_frame.grid_columnconfigure((0,1,2,3), weight=1)

def refresh_inc_table():
    for r in inc_tree.get_children(): inc_tree.delete(r)
    rows = fetch_rows("""SELECT i.id, a.name, i.date, i.flood_level, i.damage_estimate, i.casualties, i.notes
                        FROM incidents i JOIN areas a ON i.area_id = a.id ORDER BY id ASC""")
    for row in rows: inc_tree.insert("", "end", values=row)

def inc_add():
    if not inc_area.get() or not inc_date.get(): messagebox.showwarning("Missing", "Area and date required"); return
    aid = int(inc_area.get().split("ID:")[-1].replace(")",""))
    conn = get_connection(); cur = conn.cursor()
    cur.execute("INSERT INTO incidents (area_id,date,flood_level,damage_estimate,casualties,notes) VALUES (%s,%s,%s,%s,%s,%s)",
                (aid, inc_date.get(), float(inc_level.get() or 0), float(inc_damage.get() or 0), int(inc_casualties.get() or 0), inc_notes.get()))
    conn.commit(); cur.close(); conn.close()
    refresh_inc_table()

def inc_update():
    sel = inc_tree.focus()
    if not sel: messagebox.showwarning("Select", "Pick an incident"); return
    iid = inc_tree.item(sel)["values"][0]
    aid = int(inc_area.get().split("ID:")[-1].replace(")",""))
    conn = get_connection(); cur = conn.cursor()
    cur.execute("UPDATE incidents SET area_id=%s, date=%s, flood_level=%s, damage_estimate=%s, casualties=%s, notes=%s WHERE id=%s",
                (aid, inc_date.get(), float(inc_level.get() or 0), float(inc_damage.get() or 0), int(inc_casualties.get() or 0), inc_notes.get(), iid))
    conn.commit(); cur.close(); conn.close()
    refresh_inc_table()

def inc_delete():
    sel = inc_tree.focus()
    if not sel: return
    iid = inc_tree.item(sel)["values"][0]
    if not messagebox.askyesno("Confirm", f"Delete incident {iid}?"): return
    conn = get_connection(); cur = conn.cursor(); cur.execute("DELETE FROM incidents WHERE id=%s", (iid,)); conn.commit(); cur.close(); conn.close()
    refresh_inc_table()

def inc_on_select(event):
    sel = inc_tree.focus()
    if not sel: return
    vals = inc_tree.item(sel)["values"]
    inc_area.set(f"{vals[1]} (ID:{vals[0]})")
    inc_date.delete(0,"end"); inc_date.insert(0, vals[2] or "")
    inc_level.delete(0,"end"); inc_level.insert(0, vals[3] or "")
    inc_damage.delete(0,"end"); inc_damage.insert(0, vals[4] or "")
    inc_casualties.delete(0,"end"); inc_casualties.insert(0, vals[5] or "")
    inc_notes.delete(0,"end"); inc_notes.insert(0, vals[6] or "")

ctk.CTkButton(inc_btn_frame, text="Add", fg_color="#2ecc71", command=inc_add).grid(row=0,column=0, padx=8, pady=6)
ctk.CTkButton(inc_btn_frame, text="Update", fg_color="#f1c40f", command=inc_update).grid(row=0,column=1, padx=8, pady=6)
ctk.CTkButton(inc_btn_frame, text="Delete", fg_color="#e74c3c", command=inc_delete).grid(row=0,column=2, padx=8, pady=6)
ctk.CTkButton(inc_btn_frame, text="Export CSV", fg_color="#3498db", command=lambda: export_tree_to_csv(inc_tree, "incidents_export.csv")).grid(row=0,column=3, padx=8, pady=6)

inc_tree.bind("<<TreeviewSelect>>", inc_on_select)

# -----------------------
# REPORTS TAB
# -----------------------
reports_tab = tabview.tab("Reports")
reports_tab.grid_columnconfigure(0, weight=1); reports_tab.grid_rowconfigure(1, weight=1)

# report controls
rp_frame = ctk.CTkFrame(reports_tab)
rp_frame.grid(row=0,column=0, sticky="ew", padx=8, pady=8)
rp_frame.grid_columnconfigure((0,1,2,3,4), weight=1)

report_select = ctk.CTkComboBox(rp_frame, values=["Top Damage Areas","Recent Incidents","Delayed Projects","Project Status Distribution"])
report_select.set("Top Damage Areas")
report_select.grid(row=0,column=0, padx=8, pady=6, sticky="ew")

def run_report():
    choice = report_select.get()
    if choice == "Top Damage Areas":
        rows = fetch_rows("""SELECT a.name, SUM(i.damage_estimate) AS total_damage
                             FROM areas a JOIN incidents i ON a.id=i.area_id
                             GROUP BY a.id ORDER BY total_damage DESC LIMIT 10""")
        show_report_table(rows, ("Area","Total Damage (PHP)"))
        draw_bar_chart([r[0] for r in rows], [float(r[1]) for r in rows], "Top Damage by Area", ylabel="Damage (PHP)")
    elif choice == "Recent Incidents":
        rows = fetch_rows("""SELECT i.id, a.name, i.date, i.flood_level, i.damage_estimate FROM incidents i JOIN areas a ON i.area_id=a.id ORDER BY i.date DESC LIMIT 20""")
        show_report_table(rows, ("ID","Area","Date","Level(m)","Damage"))
        clear_chart()
    elif choice == "Delayed Projects":
        rows = fetch_rows("""SELECT p.id, p.project_name, a.name, p.start_date, p.end_date, p.status FROM projects p JOIN areas a ON p.area_id=a.id WHERE p.status='Delayed' ORDER BY p.start_date""")
        show_report_table(rows, ("ID","Project","Area","Start","End","Status"))
        clear_chart()
    elif choice == "Project Status Distribution":
        rows = fetch_rows("""SELECT status, COUNT(*) FROM projects GROUP BY status""")
        labels = [r[0] for r in rows]; sizes = [int(r[1]) for r in rows]
        show_report_table(rows, ("Status","Count"))
        draw_pie_chart(labels, sizes, "Projects by Status")

ctk.CTkButton(rp_frame, text="Run Report", command=run_report).grid(row=0,column=1, padx=8, pady=6)
ctk.CTkButton(rp_frame, text="Export shown table to CSV", command=lambda: export_tree_to_csv(report_tree, "report_export.csv")).grid(row=0,column=2, padx=8, pady=6)

# report results
report_table_frame = ctk.CTkFrame(reports_tab)
report_table_frame.grid(row=1,column=0, sticky="nsew", padx=8, pady=6)
report_tree = ttk.Treeview(report_table_frame, show="headings")
report_tree.pack(side="left", fill="both", expand=True, padx=6, pady=6)
report_scroll = ttk.Scrollbar(report_table_frame, orient="vertical", command=report_tree.yview)
report_tree.configure(yscroll=report_scroll.set)
report_scroll.pack(side="right", fill="y")

# chart frame
chart_frame = ctk.CTkFrame(reports_tab)
chart_frame.grid(row=2, column=0, sticky="nsew", padx=8, pady=6)
chart_frame.grid_rowconfigure(0, weight=1); chart_frame.grid_columnconfigure(0, weight=1)
chart_canvas_widget = None

def show_report_table(rows, headers):
    # clear tree
    report_tree.delete(*report_tree.get_children())
    report_tree["columns"] = headers
    for col in headers:
        report_tree.heading(col, text=col); report_tree.column(col, width=150, anchor="center")
    for r in rows:
        report_tree.insert("", "end", values=r)

def export_tree_to_csv(tree, default_name):
    path = filedialog.asksaveasfilename(defaultextension=".csv", initialfile=default_name)
    if not path: return
    cols = tree["columns"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for row in tree.get_children():
            w.writerow(tree.item(row)["values"])
    messagebox.showinfo("Exported", f"Saved to {path}")

def clear_chart():
    global chart_canvas_widget
    for widget in chart_frame.winfo_children(): widget.destroy()
    chart_canvas_widget = None

def draw_bar_chart(labels, values, title, ylabel=""):
    clear_chart()
    if not labels: return
    fig, ax = plt.subplots(figsize=(8,3))
    ax.bar(labels, values)
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.tick_params(axis='x', rotation=45, labelsize=9)
    fig.tight_layout()
    global chart_canvas_widget
    chart_canvas_widget = FigureCanvasTkAgg(fig, master=chart_frame)
    chart_canvas_widget.draw()
    chart_canvas_widget.get_tk_widget().pack(fill="both", expand=True)

def draw_pie_chart(labels, sizes, title):
    clear_chart()
    if not labels: return
    fig, ax = plt.subplots(figsize=(5,3))
    ax.pie(sizes, labels=labels, autopct='%1.1f%%', startangle=90)
    ax.set_title(title)
    global chart_canvas_widget
    chart_canvas_widget = FigureCanvasTkAgg(fig, master=chart_frame)
    chart_canvas_widget.draw()
    chart_canvas_widget.get_tk_widget().pack(fill="both", expand=True)

# -----------------------
# Utility: refresh area choices for combos
# -----------------------
def refresh_area_comboboxes():
    rows = fetch_rows("SELECT id,name FROM areas ORDER BY id ASC")
    choices = [f"{r[1]} (ID:{r[0]})" for r in rows]
    proj_area.configure(values=choices)
    inc_area.configure(values=choices)

# -----------------------
# Initial refresh functions
# -----------------------
def refresh_all():
    refresh_area_table(); refresh_proj_table(); refresh_inc_table()

refresh_all()

# -----------------------
# wire up helper functions used earlier that were defined below
# -----------------------
# export_tree_to_csv defined earlier in reports section; ensure functions exist for buttons referencing earlier
# (area/proj/inc export buttons call export_tree_to_csv used in reports — it's defined)

# run app
app.mainloop()
