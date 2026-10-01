import requests
import json
import time
import os
import threading
from dotenv import load_dotenv
load_dotenv()

# prompt_toolkit
from prompt_toolkit.application import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout
from prompt_toolkit.layout.containers import HSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl

# movegramy の関数をインポート（同じディレクトリに movegramy.py があること）
from movegramy import get_player_position

port = os.getenv("PORT")
BASE_URL   = port or "http://localhost:64123"  # 環境変数 PORT が未設定ならデフォルトを入れておく
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
    return fetch("/env/city-grammi-list") or []

# ------------------------------------------------
# アイテムをフラットな辞書に変換 { id: item_dict }
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
# 監視ループ（バックグラウンドスレッドで動かす）
# ------------------------------------------------
def monitor_loop(stop_event: threading.Event):
    print("=== Monitor スレッド開始 ===")
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

    while not stop_event.is_set():
        try:
            iteration += 1

            cur_buildings = to_dict(fetch_buildings(uuid), prefix="b")
            cur_grammi    = to_dict(fetch_grammi(),        prefix="g")

            b_added, b_removed, b_changed = diff(prev_buildings, cur_buildings)
            g_added, g_removed, g_changed = diff(prev_grammi,    cur_grammi)

            has_change = any([b_added, b_removed, b_changed, g_added, g_removed, g_changed])

            if has_change:
                print(f"\n--- #{iteration}  変更検知  ({time.strftime('%H:%M:%S')}) ---")
                # 差分情報の表示をなし
                # print_diff("Building", b_added, b_removed, b_changed)
                # print_diff("Grammi",   g_added, g_removed, g_changed)

                write_txt(cur_buildings, cur_grammi)
                print(f"  → {OUTPUT_TXT} を更新しました")

                prev_buildings = cur_buildings
                prev_grammi    = cur_grammi

            # stop_event.wait を使うと中断時に素早く抜けられる
            stop_event.wait(INTERVAL)

        except Exception as e:
            print(f"[Monitor エラー] {e}")
            # 少し待ってから続行
            if stop_event.wait(1):
                break

    print("=== Monitor スレッド終了 ===")

# ------------------------------------------------
# prompt_toolkit を使ったキー監視（メインスレッドで実行）
# ------------------------------------------------
def start_key_listener(stop_event: threading.Event):
    """
    この関数はメインスレッドで呼び出し、Application.run() をブロッキング実行します。
    キー入力で get_player_position を別スレッドで呼び出します。
    'g' と 'c-g'（Ctrl+G）をバインドしています。
    端末によって Shift+Enter は区別されないため 's-enter' は使いません。
    """
    kb = KeyBindings()

    @kb.add('g')
    def _(event):
        print("[キー] 'g' を検出しました。get_player_position を呼び出します。")
        threading.Thread(target=get_player_position, daemon=True).start()

    @kb.add('c-g')
    def _(event):
        print("[キー] Ctrl+G を検出しました。get_player_position を呼び出します。")
        threading.Thread(target=get_player_position, daemon=True).start()

    @kb.add('c-c')
    def _(event):
        print("\n[キーリスナー] Ctrl+C で停止要求を受信しました。")
        event.app.exit()

    # 画面に簡単なヘルプを表示
    help_text = [
        ("class:title", "Omega Monitor キーリスナー\n"),
        ("", "  - g        : movegramy.get_player_position を呼び出す\n"),
        ("", "  - Ctrl+G   : 同上（代替）\n"),
        ("", "  - Ctrl+C   : プログラム終了\n"),
        ("", "\n注意: 多くの端末は Shift+Enter を区別しません。Shift+Enter を必須にしたい場合は別手段（外部ホットキーやシグナル）を検討してください。\n"),
    ]
    root_container = HSplit([
        Window(content=FormattedTextControl(help_text), height=8, wrap_lines=True),
    ])
    layout = Layout(root_container)

    app = Application(layout=layout, key_bindings=kb, full_screen=False)

    try:
        # run() 中は Ctrl+C が KeyboardInterrupt にならずキー 'c-c' になる
        app.run()
    except KeyboardInterrupt:
        print("\n[キーリスナー] Ctrl+C で停止要求を受信しました。")
    except Exception as e:
        print(f"[キーリスナー] 例外: {e}")
    finally:
        # 終了時に停止イベントを立てる（監視スレッドを終了させる）
        stop_event.set()
        # Application を安全に終了（run が例外で落ちている可能性があるため）
        try:
            app.exit()
        except Exception:
            pass

# ------------------------------------------------
# メイン
# ------------------------------------------------
def main():
    print("=== Omega Monitor 起動 ===")
    print(f"  確認間隔    : {INTERVAL}秒")
    print(f"  出力ファイル: {OUTPUT_TXT}")
    print("  'g' または Ctrl+G で movegramy.get_player_position を呼び出します。")
    print("  Ctrl+C で停止\n")
    time.sleep(1)

    stop_event = threading.Event()

    # 監視ループをバックグラウンドスレッドで開始
    monitor_thread = threading.Thread(target=monitor_loop, args=(stop_event,), daemon=True)
    monitor_thread.start()

    # キーリスナーはメインスレッドでブロッキング実行（ここで Ctrl+C を受け取る）
    start_key_listener(stop_event)

    # キーリスナーが終了して stop_event が立ったら監視スレッドの終了を待つ
    stop_event.set()
    monitor_thread.join(timeout=3)
    print("=== Omega Monitor 終了 ===")

if __name__ == "__main__":
    main()
