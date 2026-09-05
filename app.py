import traceback
from flask import Flask, request, jsonify
from scripts.shunting_plan import ShuntingPlan
from scripts import parser as seq_parser
from rag import qa

app = Flask(__name__)


@app.route("/")
def index():
    return app.send_static_file("index.html")


@app.route("/qa")
def qa_page():
    return app.send_static_file("qa.html")


@app.route("/api/solve", methods=["POST"])
def solve():
    """调车表法（按站顺编组）求解。

    请求：{"seq": "…", "station_order": null, "home_track": "10",
            "allowed_tracks": [...] | "track_budget": n, "depart_track": "DF5",
            "weights": {pull,throw,transfer}}
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

        if not seq:
            return jsonify({"error": "待编车列为空"}), 400
        # 解析校验（抛出 ParseError → 400）
        groups = seq_parser.parse_seq(seq, station_order)
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


@app.route("/api/qa", methods=["POST"])
def api_qa():
    """教材问答：检索相关片段 + DeepSeek 生成回答（未配置 key 时降级为仅返回原文）"""
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
    app.run(host="0.0.0.0", port=50000, debug=True, threaded=True)
