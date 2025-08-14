from flask import Flask, request, jsonify
app = Flask(__name__)
@app.route("/")
def hello():
    return "Hello, the secure AI service is up!"
@app.route("/estimate")
def estimate():
    try:
        nodes = int(request.args.get("nodes", 1))
        hours = int(request.args.get("hours", 1))
    except (ValueError, TypeError):
        return (
            jsonify({"error": "Invalid input. 'nodes' and 'hours' must be integers."}),
            400,
        )

    if nodes <= 0 or hours <= 0:
        return (
            jsonify({"error": "'nodes' and 'hours' must be positive integers."}),
            400,
        )

    cost_per_node_hour = 10
    total_cost = nodes * hours * cost_per_node_hour
    return jsonify({"nodes": nodes, "hours": hours, "estimated_cost_usd": total_cost})
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
