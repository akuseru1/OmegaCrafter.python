import requests
import json
import time
import os
import threading
from dotenv import load_dotenv

# prompt_toolkit を使ってターミナルのキー入力を監視する
from prompt_toolkit.application import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout
from prompt_toolkit.layout.containers import HSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl

# movegramy の関数をインポート（同じディレクトリに movegramy.py があること）
from movegramy import get_player_position

port = os.getenv("PORT")
BASE_URL   = port
INTERVAL   = 3         # 確認間隔（秒）
OUTPUT_TXT = "txt/OmegaCrafter.txt"  # 書き込み先テキストファイル

# ------------------------------------------------
# API取得
# ------------------------------------------------
def fetch(path, params=None):
    try:
        resp = requests.get(f"{BASE_URL}{path}", params=params, timeout=2)
        return resp.json()
    except Exception:
        return None

def fetch_city_list():
    return fetch("/env/city-list") or []

def fetch_buildings(uuid):
    return fetch("/city/building-list", params={"uuid": uuid}) or []

def fetch_grammi():
    return fetch("/env/city-grammi-list") or []  # 修正: /env/city-grammi-list

# ------------------------------------------------
# アイテムをフラットな辞書に変換 { id: item_dict }
# id キーがない場合は uuid / name / インデックスで代用
# ------------------------------------------------
def to_dict(items, prefix=""):
    result = {}
    if isinstance(items, list):
        for i, item in enumerate(items):
            if isinstance(item, dict):
                key = item.get("id") or item.get("uuid") or item.get("name") or f"{prefix}{i}"
                result[str(key)] = item
            else:
                result[f"{prefix}{i}"] = item
    elif isinstance(items, dict):
        for k, v in items.items():
            result[str(k)] = v
    return result

# ------------------------------------------------
# テキストファイルへ書き込み
# ------------------------------------------------
def write_txt(buildings: dict, grammi: dict):
    lines = []

    # --- Buildings ---
    lines.append("=" * 50)
    lines.append("  BUILDINGS")
    lines.append("=" * 50)
    if buildings:
        for key, item in sorted(buildings.items()):
            lines.append(f"[{key}]")
            if isinstance(item, dict):
                for k, v in item.items():
                    lines.append(f"  {k}: {v}")
            else:
                lines.append(f"  {item}")
            lines.append("")
    else:
        lines.append("  （アイテムなし）")
        lines.append("")

    # --- Grammi ---
    lines.append("=" * 50)
    lines.append("  GRAMMI")
    lines.append("=" * 50)
    if grammi:
        for key, item in sorted(grammi.items()):
            lines.append(f"[{key}]")
            if isinstance(item, dict):
                for k, v in item.items():
                    lines.append(f"  {k}: {v}")
            else:
                lines.append(f"  {item}")
            lines.append("")
    else:
        lines.append("  （アイテムなし）")
        lines.append("")

    lines.append(f"最終更新: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    # 出力先フォルダがなければ作成
    out_dir = os.path.dirname(OUTPUT_TXT)
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir, exist_ok=True)

    with open(OUTPUT_TXT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

# ------------------------------------------------
# 差分ログをコンソールに表示
# ------------------------------------------------
def print_diff(label, added, removed, changed):
    if added:
        for k, v in added.items():
            print(f"  [追加] {label} [{k}]  →  {v}")
    if removed:
        for k in removed:
            print(f"  [削除] {label} [{k}]")
    if changed:
        for k, (old, new) in changed.items():
            print(f"  [変更] {label} [{k}]")
            if isinstance(old, dict) and isinstance(new, dict):
                for field in set(list(old.keys()) + list(new.keys())):
                    ov = old.get(field)
                    nv = new.get(field)
                    if ov != nv:
                        print(f"         {field}: {ov}  →  {nv}")
            else:
                print(f"         {old}  →  {new}")

def diff(old: dict, new: dict):
    added   = {k: v for k, v in new.items() if k not in old}
    removed = {k: v for k, v in old.items() if k not in new}
    changed = {k: (old[k], new[k]) for k in old if k in new and old[k] != new[k]}
    return added, removed, changed

# ------------------------------------------------
# prompt_toolkit を使ったキー監視（Shift+Enter と 'g' の両方をトリガー）
# ------------------------------------------------
def start_key_listener():
    """
    prompt_toolkit の Application を作成して run() します。
    run() はブロッキングなので別スレッドで起動することを想定しています。
    Shift+Enter の捕捉は端末に依存するため、念のため 'g' キーもトリガーとして追加しています。
    """
    kb = KeyBindings()

    # @kb.add('s-enter')
    # def _(event):
    #     # Shift+Enter 検出時に movegramy.get_player_position を別スレッドで呼び出す
    #     print("[キー] Shift+Enter を検出しました。get_player_position を呼び出します。")
    #     threading.Thread(target=get_player_position, daemon=True).start()

    @kb.add('g')
    def _(event):
        # 代替トリガー（端末が Shift+Enter を送らない場合の保険）
        print("[キー] 'g' を検出しました。get_player_position を呼び出します。")
        threading.Thread(target=get_player_position, daemon=True).start()

    # 画面に簡単なヘルプを表示するためのレイアウト（必須ではないが視認性向上）
    help_text = [
        ("class:title", "Omega Monitor キーリスナー\n"),
        ("", "  - Shift+Enter : movegramy.get_player_position を呼び出す（端末により動作しない場合あり）\n"),
        ("", "  - g           : 上と同等の代替トリガー\n"),
        ("", "  - Ctrl+C      : プログラム終了\n"),
    ]
    root_container = HSplit([
        Window(content=FormattedTextControl(help_text), height=6, wrap_lines=True),
    ])
    layout = Layout(root_container)

    app = Application(layout=layout, key_bindings=kb, full_screen=False)
    try:
        app.run()
    except Exception as e:
        # キーリスナーが予期せず止まった場合のログ
        print(f"[キーリスナー] 実行中に例外が発生しました: {e}")

# ------------------------------------------------
# メイン
# ------------------------------------------------
def main():
    print("=== Omega Monitor 起動 ===")
    print(f"  確認間隔    : {INTERVAL}秒")
    print(f"  出力ファイル: {OUTPUT_TXT}")
    print("  Shift+Enter または 'g' で movegramy.get_player_position を呼び出します。")
    print("  Ctrl+C で停止\n")
    time.sleep(1)

    # キー監視を別スレッドで開始（daemon にしてメイン終了時に自動終了）
    key_thread = threading.Thread(target=start_key_listener, daemon=True)
    key_thread.start()

    # 初回 UUID 取得
    cities = fetch_city_list()
    uuid = "5e9b64700b8349bab7aaa1ccacf5c05a"
    if isinstance(cities, list) and cities:
        first = cities[0]
        if isinstance(first, dict):
            uuid = first.get("Uuid") or first.get("uuid") or first.get("id") or uuid
    elif isinstance(cities, dict):
        uuid = cities.get("Uuid") or cities.get("uuid") or uuid

    prev_buildings: dict = {}
    prev_grammi:    dict = {}
    iteration = 0

    while True:
        try:
            iteration += 1

            cur_buildings = to_dict(fetch_buildings(uuid), prefix="b")
            cur_grammi    = to_dict(fetch_grammi(),        prefix="g")

            b_added, b_removed, b_changed = diff(prev_buildings, cur_buildings)
            g_added, g_removed, g_changed = diff(prev_grammi,    cur_grammi)

            has_change = any([b_added, b_removed, b_changed, g_added, g_removed, g_changed])

            if has_change:
                print(f"\n--- #{iteration}  変更検知  ({time.strftime('%H:%M:%S')}) ---")
                print_diff("Building", b_added, b_removed, b_changed)
                print_diff("Grammi",   g_added, g_removed, g_changed)

                write_txt(cur_buildings, cur_grammi)
                print(f"  → {OUTPUT_TXT} を更新しました")

                prev_buildings = cur_buildings
                prev_grammi    = cur_grammi

            time.sleep(INTERVAL)

        except KeyboardInterrupt:
            print("\n\n監視を停止しました。")
            break
        except Exception as e:
            # 例外発生時はログを表示して短時間待って再試行
            print(f"[エラー] ループ内で例外が発生しました: {e}")
            time.sleep(1)

if __name__ == "__main__":
    main()