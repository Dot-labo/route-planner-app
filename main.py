import googlemaps
import streamlit as st
from streamlit_sortables import sort_items
import folium
from streamlit_folium import st_folium
from folium.plugins import PolyLineTextPath
from ortools.constraint_solver import pywrapcp, routing_enums_pb2
import math
import uuid
import sqlite3
import pandas as pd

st.set_page_config(layout="wide")
st.subheader("お弁当配送ルート最適化アプリ")

# === SQLite データベース初期化 ===ローカルとデプロイ時で切り替え必要
#conn = sqlite3.connect("locations.db")
conn = sqlite3.connect("/mnt/data/locations.db")

c = conn.cursor()
c.execute("""
    CREATE TABLE IF NOT EXISTS locations (
        name TEXT PRIMARY KEY,
        address TEXT NOT NULL,
        route TEXT
    )
""")
conn.commit()

# === 管理画面と操作画面の切り替え ===
page = st.sidebar.radio("表示切り替え", ["操作画面", "管理画面"])

# === 管理画面 ===
if page == "管理画面":
    st.subheader("📥 GLUGデータ取込み")
    fixed_routes = ["全項目", "A", "B①", "B②", "C", "D", "E", "F", "G", "その他"]
    selected_route = st.selectbox("対象の配送ルートを選択してください", fixed_routes, key="route_selection_fixed")

    glug_file = st.file_uploader("GLUG形式のCSVファイルを選択（C列：施設名、G列：都道府県、H+I列：住所、AB列：ルート名）", type="csv", key="glug_import")

    if glug_file is not None:
        try:
            df_glug = pd.read_csv(glug_file, header=None, skiprows=1, encoding='cp932')
            imported_count = 0
            for _, row in df_glug.iterrows():
                name = str(row[2]).strip() if not pd.isna(row[2]) else ""
                prefecture = str(row[6]).strip() if not pd.isna(row[6]) else ""
                city = str(row[7]).strip() if not pd.isna(row[7]) else ""
                address = str(row[8]).strip() if not pd.isna(row[8]) else ""
                route = str(row[27]).strip() if not pd.isna(row[27]) else ""
                full_address = f"{prefecture}{city}{address}"

                if name and full_address and name != "出発地":
                    if selected_route == "全項目" or route == selected_route:
                        c.execute("REPLACE INTO locations (name, address, route) VALUES (?, ?, ?)", (name, full_address, route))
                        imported_count += 1

            conn.commit()
            st.success(f"{imported_count} 件の施設をインポートしました")
            st.rerun()

        except Exception as e:
            st.error("GLUGインポート中にエラーが発生しました。")
            st.exception(e)
            
    st.subheader("📋 配送先の編集")
    with st.form("add_form"):
        name = st.text_input("名称")
        address = st.text_input("住所")
        route = st.text_input("ルート（任意）")
        submitted = st.form_submit_button("追加・更新")
        if submitted and name and address:
            c.execute("REPLACE INTO locations (name, address, route) VALUES (?, ?, ?)", (name, address, route))
            conn.commit()
            st.success(f"{name} を追加・更新しました")

    st.markdown("---")
    st.subheader("登録済み一覧")

    rows = c.execute("SELECT name, address, route FROM locations").fetchall()

    if "delete_check_states" not in st.session_state:
        st.session_state["delete_check_states"] = {name: False for name, _, _ in rows if name != "出発地"}

    all_selected = all(st.session_state["delete_check_states"].values())
    if st.button("✅ 全選択" if not all_selected else "❌ 全解除", key="toggle_all_delete"):
        for name in st.session_state["delete_check_states"]:
            st.session_state["delete_check_states"][name] = not all_selected

    delete_targets = []
    with st.form("delete_form"):
        for name, address, route in rows:
            if name == "出発地":
                continue
            checked = st.checkbox(
                f"**{name}**：{address}（ルート：{route}）",
                value=st.session_state["delete_check_states"].get(name, False),
                key=f"chk_{name}"
            )
            st.session_state["delete_check_states"][name] = checked
            if checked:
                delete_targets.append(name)

        if st.form_submit_button("チェックした項目を一括削除"):
            for name in delete_targets:
                c.execute("DELETE FROM locations WHERE name = ?", (name,))
            conn.commit()
            st.success(f"{len(delete_targets)} 件の項目を削除しました")
            del st.session_state["delete_check_states"]
            st.rerun()

    st.subheader("🚚 出発地を設定")
    with st.form("start_form"):
        start_address_input = st.text_input("出発地の住所", "")
        submitted_start = st.form_submit_button("出発地を登録・更新")
        if submitted_start and start_address_input:
            c.execute("REPLACE INTO locations (name, address, route) VALUES (?, ?, '')", ("出発地", start_address_input))
            conn.commit()
            st.success("✅ 出発地を登録・更新しました")

    st.subheader("📤 データエクスポート")
    df = pd.read_sql_query("SELECT name, address, route FROM locations WHERE name != '出発地'", conn)
    csv = df.to_csv(index=False).encode("utf-8-sig")
    st.download_button("CSVをダウンロード", csv, "locations.csv", "text/csv")

    st.subheader("📥 データインポート")
    uploaded_file = st.file_uploader("CSVファイルを選択（列順：名称,住所,ルート）", type="csv")
    if uploaded_file is not None:
        try:
            df_new = pd.read_csv(uploaded_file, header=None, encoding='utf-8-sig')
            df_new = df_new.iloc[:, :3]
            df_new.columns = ['name', 'address', 'route']
            for _, row in df_new.iterrows():
                name = str(row['name']).strip()
                address = str(row['address']).strip()
                route = str(row['route']).strip()
                if name and address and name != '出発地':
                    c.execute("REPLACE INTO locations (name, address, route) VALUES (?, ?, ?)", (name, address, route))
            conn.commit()
            st.success("CSVからデータをインポートしました")
            st.rerun()
        except Exception as e:
            st.error("インポート中にエラーが発生しました。")
            st.exception(e)
    st.stop()

### === 操作画面ここから　データ取得（操作画面側などに使う用） ===
rows = c.execute("SELECT name, address, route FROM locations").fetchall()
if not rows:
    st.warning("⚠️ 管理画面から配送先を登録してください")
    st.stop()

# === 地点定義 ===
locations = {
    name: {
        "address": address,
        "route": route
    }
    for name, address, route in rows
}
start_name = "出発地"
if start_name not in locations:
    st.error(f"出発地「{start_name}」が登録されていません。管理画面で登録してください。")
    st.stop()
start_address = locations[start_name]["address"]

# 🔐 Google APIキー
API_KEY = "AIzaSyAM9BWoMdPIqRId7aUDHD9lIdS82A7A9zA"
gmaps = googlemaps.Client(key=API_KEY)

# === ジオコーディング関数 ===
@st.cache_data(show_spinner=False)
def geocode_address(address):
    try:
        result = gmaps.geocode(address)
        if result and 'geometry' in result[0]:
            loc = result[0]['geometry']['location']
            return (loc['lat'], loc['lng'])
    except:
        return None
    return None

# === 座標取得 ===
coords = {}
missing = []
for name, info in locations.items():
    loc = geocode_address(info["address"])
    if loc:
        coords[name] = loc
    else:
        missing.append(f"{name}（{info['address']}）")

if missing:
    st.error("以下の地点の座標取得に失敗しました。住所を見直してください。")
    for m in missing:
        st.error(f"❌ {m}")
    st.stop()

# === 距離計算 ===
def calc_distance(p1, p2):
    lat1, lon1 = coords[p1]
    lat2, lon2 = coords[p2]
    radius = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return radius * c * 1000

# === 並び順のモード選択（手動 or AI） ===
mode = st.radio("訪問順の設定方法を選択", ["①手動で変更", "②AIで自動最適化"], horizontal=True, index=1, key="route_mode")
manual_mode = (mode == "①手動で変更")

# === フィルタ処理 ===
st.subheader("配送ルートはサイドバーで選択（スマホ：左上の「>>」マーク）")
fixed_routes = ["全項目", "A", "B①", "B②", "C", "D", "E", "F", "G", "その他"]
selected_route = st.sidebar.selectbox("🚚 配送ルートを選択", fixed_routes, key="route_filter")
# 本体側に遷移したことを明示（選択後に表示）
st.write(f"✅ 「{selected_route}」ルートを選択しました")

filtered_locations = {
    name: info for name, info in locations.items()
    if name != "出発地" and (selected_route == "全項目" or info["route"] == selected_route)
}

if not filtered_locations:
    st.warning("このルートには対象施設がありません。")
    st.stop()

# 🚀 フィルタ変更時に自動でルート計算（AIモード時）
if not manual_mode:
    def run_auto_route_update(selected_names):
        start_name = "出発地"
        route_names = [start_name] + selected_names
        if not route_names or len(route_names) < 2:
            return

        matrix = []
        for from_name in route_names:
            row = []
            for to_name in route_names:
                dist = 0 if from_name == to_name else int(calc_distance(from_name, to_name))
                row.append(dist)
            matrix.append(row)

        manager = pywrapcp.RoutingIndexManager(len(matrix), 1, 0)
        routing = pywrapcp.RoutingModel(manager)

        def distance_callback(from_idx, to_idx):
            return matrix[manager.IndexToNode(from_idx)][manager.IndexToNode(to_idx)]

        transit_idx = routing.RegisterTransitCallback(distance_callback)
        routing.SetArcCostEvaluatorOfAllVehicles(transit_idx)

        search_params = pywrapcp.DefaultRoutingSearchParameters()
        search_params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
        solution = routing.SolveWithParameters(search_params)

        if not solution:
            return

        index = routing.Start(0)
        ordered_route = []
        while not routing.IsEnd(index):
            ordered_route.append(route_names[manager.IndexToNode(index)])
            index = solution.Value(routing.NextVar(index))
        ordered_route.append(route_names[manager.IndexToNode(index)])

        total = 0
        for i in range(len(ordered_route) - 1):
            total += calc_distance(ordered_route[i], ordered_route[i + 1])

        st.session_state["last_route"] = ordered_route
        st.session_state["last_total_distance"] = total
        st.session_state["ordered_names"] = [name for name in ordered_route if name != start_name]

    # 自動で更新（選択されている施設だけ）
    if "school_check_states" not in st.session_state:
        st.session_state["school_check_states"] = {name: True for name in filtered_locations}

    selected_names = [name for name, state in st.session_state["school_check_states"].items() if state and name in filtered_locations]

    if selected_names:
        run_auto_route_update(selected_names)

# === 地図描画 ===
try:
    if "last_route" not in st.session_state or not st.session_state["last_route"]:
        pass
    else:
        valid_route = [place for place in st.session_state["last_route"] if coords.get(place)]
        line_coords = [coords[place] for place in valid_route]

        m = folium.Map(location=[35.0, 135.0], zoom_start=13)
        m.fit_bounds(line_coords)

        circled_numbers = ['①','②','③','④','⑤','⑥','⑦','⑧','⑨','⑩','⑪','⑫','⑬','⑭','⑮']
        for i, place in enumerate(valid_route):
            lat, lon = coords[place]
            number = circled_numbers[i] if i < len(circled_numbers) else str(i + 1)
            address = locations.get(place, "")

            if i == 0:
                folium.Marker(
                    location=(lat, lon),
                    popup="出発地",
                    icon=folium.Icon(color="green", icon="play")
                ).add_to(m)

            folium.Marker(
                location=(lat, lon),
                icon=folium.DivIcon(html=f"""
                    <div style='display: flex; align-items: center; justify-content: center; 
                                width: 32px; height: 32px; border-radius: 50%; background: white; 
                                border: 2px solid red; color: red; font-size: 16pt; font-weight: bold;
                                box-shadow: 0 0 4px #888;'>{number}</div>
                """)
            ).add_to(m)

            folium.map.Marker(
                [lat, lon],
                icon=folium.DivIcon(html=f"""
                    <div style='font-size: 12pt; color: black; 
                                margin-left: 38px; width: 200px; word-wrap: break-word;
                                text-shadow: -1px -1px 0 white, 1px -1px 0 white,
                                            -1px 1px 0 white, 1px 1px 0 white;'>
                        {place}<br>
                        <span style='font-size:10pt; color: black;
                                    text-shadow: -1px -1px 0 white, 1px -1px 0 white,
                                                -1px 1px 0 white, 1px 1px 0 white;'>
                            {address}
                        </span>
                    </div>
                """)
            ).add_to(m)

        polyline = folium.PolyLine(line_coords, color='blue', weight=5)
        polyline.add_to(m)

        arrow = PolyLineTextPath(polyline, ' ➔ ', repeat=True, offset=7,
                                 attributes={'font-size': '18px', 'color': 'red'})
        m.add_child(arrow)

        st_folium(m, height=600, width="90%")
except Exception as e:
    st.error("❌ 地図の表示に失敗しました。")
    st.exception(e)

# === 🚚 所要時間表示 ===
per_stop_time_min = 5
ordered_route = st.session_state.get("last_route", [])
total = st.session_state.get("last_total_distance", None)

if ordered_route and total is not None:
    num_stops = len(ordered_route) - 2  # 出発地と戻り地を除く中間地点数

    def estimate_time(kmh, total_distance_m, stops, stop_time_min):
        travel_time_min = (total_distance_m / 1000) / kmh * 60
        return round(travel_time_min + (stops * stop_time_min))

    st.markdown("#### 🚚 平均速度ごとの予想所要時間（※各配達先での対応時間：5分）")
    cols = st.columns(3)
    for i, speed in enumerate([30, 40, 50]):
        est_min = estimate_time(speed, total, num_stops, per_stop_time_min)

        with cols[i]:
            st.caption(f"{speed} km/h")  # 小さめのラベル
            st.text(f"{est_min} 分")  # 大きめの数値と単位

# === 訪問対象の選択 ===
st.subheader("訪問対象を選択してください")
all_selected = all(st.session_state.get("school_check_states", {}).values())
toggle = st.button("✅ 全て選択" if not all_selected else "❌ 全て解除")
if toggle:
    for name in st.session_state["school_check_states"]:
        st.session_state["school_check_states"][name] = not all_selected

selected_names = []
cols = st.columns(3)
for i, name in enumerate(filtered_locations):
    with cols[i % 3]:
        if name not in st.session_state["school_check_states"]:
            st.session_state["school_check_states"][name] = True

        checked = st.checkbox(name, value=st.session_state["school_check_states"][name], key=f"school_{name}")
        st.session_state["school_check_states"][name] = checked
        if checked:
            selected_names.append(name)

if len(selected_names) == 0:
    st.warning("1つ以上の学校を選択してください")
    st.stop()

# === 訪問順表示 ===
if "last_route" in st.session_state:
    ordered = st.session_state["last_route"]
    if len(ordered) >= 2:
        start = ordered[0]
        end = ordered[-1]
        middle_points = ordered[1:-1]

        st.markdown("### 🧭 訪問順:")
        st.write(f"出発地：{start}")

        circled_numbers = ['①','②','③','④','⑤','⑥','⑦','⑧','⑨','⑩','⑪','⑫','⑬','⑭','⑮']
        middle_html = []

        for i, name in enumerate(middle_points):
            circled = circled_numbers[i] if i < len(circled_numbers) else str(i + 1)
            address = locations.get(name, {}).get("address", "")
            middle_html.append(f'<span title="{address}">{circled} {name}</span>')

        joined_html = " ➔ ".join(middle_html)
        st.markdown(joined_html, unsafe_allow_html=True)
        st.write(f"戻り地：{end}")