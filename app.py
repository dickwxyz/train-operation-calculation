import traceback
from flask import Flask, request, jsonify
from scripts.shunting_plan import ShuntingPlan
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
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "请求体为空"}), 400

        cars_raw = data.get("cars", [])
        num_tracks = data.get("num_tracks", 3)
        target_order = data.get("target_order", [])

        # 校验：车辆列表
        if not cars_raw or len(cars_raw) < 2:
            return jsonify({"error": "车辆至少需要2辆"}), 400

        cars = []
        seen_ids = set()
        for item in cars_raw:
            car_id = item.get("id", "").strip()
            dest = item.get("dest", "").strip()
            if not car_id:
                return jsonify({"error": "存在空车号，请检查输入"}), 400
            if not dest:
                return jsonify({"error": f"车号{car_id}的去向为空"}), 400
            if car_id in seen_ids:
                return jsonify({"error": f"车号{car_id}重复"}), 400
            seen_ids.add(car_id)
            cars.append((car_id, dest))

        # 校验：股道数
        if not isinstance(num_tracks, int) or num_tracks < 2 or num_tracks > 6:
            return jsonify({"error": "股道数须为2~6的整数"}), 400

        # 校验：目标顺序
        if not target_order:
            return jsonify({"error": "请设置目标编组顺序"}), 400

        # 校验：去向是否都能在目标顺序中找到
        all_dests = set(d for _, d in cars)
        for d in all_dests:
            if d not in target_order:
                return jsonify({"error": f"去向'{d}'不在目标编组顺序中"}), 400

        # 求解
        planner = ShuntingPlan(cars, num_tracks, target_order)
        result = planner.solve()

        return jsonify({"success": True, **result})

    except ValueError as e:
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
