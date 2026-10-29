import os
import traceback
from flask import Flask, request, jsonify
from scripts.shunting_plan import ShuntingPlan
from scripts import parser as seq_parser
from scripts import mode as appmode
from scripts.build_bianzu_page import render_bianzu_panel
from scripts.rag import qa

app = Flask(__name__)


@app.route("/")
def index():
    return app.send_static_file("index.html")


@app.route("/qa")
def qa_page():
    return app.send_static_file("qa.html")


@app.route("/bianzu")
def bianzu_page():
    """技术站列车编组计划算例演示页（静态生成）。"""
    return app.send_static_file("bianzu.html")


@app.route("/svg/bianzu/<path:filename>")
def bianzu_svg(filename):
    """bianzu.html 用相对路径引用到达站图；与 /style.css 同理补一条映射。"""
    return app.send_static_file(os.path.join("svg", "bianzu", filename))


@app.route("/api/bianzu", methods=["POST"])
def api_bianzu():
    """编组算例页：接收编辑后的 T集/t节/车流，返回重算后的 panel HTML。"""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "请求体必须是 JSON 对象"}), 400
    try:
        html = render_bianzu_panel(
            data.get("key"), data.get("T"), data.get("t"), data.get("N"))
        return jsonify({"success": True, "html": html})
    except (ValueError, TypeError) as e:
        return jsonify({"error": str(e)}), 400


@app.route("/style.css")
def style_css():
    """页面用相对路径引用样式（托管平台把 static/ 当作站点根时才能解析）；
    本地 Flask 下 / 与 /qa 的相对路径都会落到 /style.css，这里补一条映射。"""
    return app.send_static_file("style.css")


@app.route("/api/solve", methods=["POST"])
def solve():
    """调车表法（按站顺编组）求解。

    请求：{"seq": "…", "station_order": null, "home_track": "10",
            "allowed_tracks": [...] | "track_budget": n, "depart_track": "DF5",
            "weights": {pull,throw,transfer},
            "deep_merge": false}   // true = 额外枚举二·四·五三列暂合（例4.4/习题3）
    返回：{success, meta, stages{xialuo,tiaozheng}, schemes[], best_scheme_id}
    校验规则与 static/index.html 的 validate 函数保持一致（改输入规则需同步两处）。
    """
    try:
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"error": "请求体为空"}), 400

        seq = (data.get("seq") or "").strip()
        station_order = data.get("station_order") or None
        home = str(data.get("home_track") or "10").strip()
        depart = str(data.get("depart_track") or "DF").strip()
        weights = data.get("weights")
        deep_merge = bool(data.get("deep_merge"))

        if not seq:
            return jsonify({"error": "待编车列为空"}), 400
        # 解析校验（抛出 ParseError → 400）
        groups = seq_parser.parse_seq(seq, station_order)
        # 教学锁定：白名单——只放行例题。判定用「站号重命名 + 车组改写均不变」的规范形，
        # 因此习题原题、各种变形、自编数据都进不来。闸门只在此 HTTP 边界，
        # 库层 planner/ShuntingPlan 不受影响。
        if appmode.LOCKED and not appmode.is_allowed(groups):
            return jsonify({"error": appmode.reject_message(groups)}), 403
        if sum(g.count for g in groups) < 2:
            return jsonify({"error": "待编车辆至少 2 辆"}), 400

        allowed = data.get("allowed_tracks")
        budget = data.get("track_budget")
        if allowed is not None:
            allowed = [str(t).strip() for t in allowed if str(t).strip()]
            if home not in allowed:
                allowed.insert(0, home)     # home 恒为可作业道
            if not allowed:
                return jsonify({"error": "可用股道为空"}), 400
        elif budget is not None:
            if not isinstance(budget, int) or budget < 1 or budget > 10:
                return jsonify({"error": "track_budget 须为 1~10 的整数"}), 400
        if not depart:
            return jsonify({"error": "出发股道为空"}), 400
        if weights is not None and not isinstance(weights, dict):
            return jsonify({"error": "weights 须为对象"}), 400

        result = ShuntingPlan(
            seq, home_track=home, allowed_tracks=allowed,
            track_budget=budget, depart_track=depart,
            station_order=station_order, weights=weights,
            deep_merge=deep_merge,
        ).solve()

        if not result["schemes"]:
            return jsonify({
                "success": True,
                **result,
                "note": "在当前可用股道数下无可运行的暂合方案（调度无法收敛）。",
            })
        return jsonify(result)

    except seq_parser.ParseError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": f"服务器内部错误: {str(e)}"}), 500


@app.route("/api/mode")
def api_mode():
    """当前运行模式，供前端决定习题按钮是否放开（接口不可达时前端按锁定降级）。"""
    resp = jsonify(appmode.mode_payload())
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/api/qa", methods=["POST"])
def api_qa():
    """教材问答：章节级检索 + DeepSeek 组织答案（严格依据教材片段）"""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "请求体为空"}), 400

    question = (data.get("question") or "").strip()
    if not question:
        return jsonify({"error": "问题不能为空"}), 400
    if len(question) > 500:
        return jsonify({"error": "问题过长（不超过500字）"}), 400

    try:
        result = qa.answer(question)
        return jsonify({"success": True, **result})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": f"服务器内部错误: {str(e)}"}), 500


if __name__ == "__main__":
    import os
    # 托管平台（如 PocketBay）通过 PORT 注入端口；本地默认仍为 50000。
    port = int(os.environ.get("PORT", 50000))
    debug = os.environ.get("FLASK_DEBUG", "").lower() in ("1", "true", "yes")
    print(f"[mode] 教学闸门：{'锁定（只放行例题）' if appmode.LOCKED else '关闭（完整版）'}"
          f"（MODE={appmode.MODE}）")
    app.run(host="0.0.0.0", port=port, debug=debug, threaded=True)
