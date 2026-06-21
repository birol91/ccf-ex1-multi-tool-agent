"""
Flask web chat for Exercise 1 — Multi-Tool Support Agent (CCA-F).

A thin web layer over agent.py. It does NOT reimplement the agentic loop, the tools, the
Excel mock DB, the structured errors, or the hook — it imports and reuses them. The only new
responsibilities here are:
  - keep the conversation history between HTTP requests (in-memory, per session id);
  - turn the refund confirmation into an in-chat yes/no instead of a terminal input().

Learning/demo only: no auth, no real DB, no websockets. One process, in-memory state.
"""

import uuid

from flask import Flask, jsonify, render_template, request

from agent import ConfirmationRequired, run_agent_web

app = Flask(__name__)

# session_id -> {"messages": [...], "pending_refund": {...} | None}
# In-memory only; restarting the server clears all conversations (fine for a demo).
SESSIONS = {}

YES = {"yes", "y", "evet", "e", "onayliyorum", "onay"}
NO = {"no", "n", "hayir", "iptal"}


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json(force=True)
    user_text = (data.get("message") or "").strip()
    session_id = data.get("session_id") or uuid.uuid4().hex

    session = SESSIONS.setdefault(session_id, {"messages": [], "pending_refund": None})

    # --- Case 1: we are waiting for a yes/no on a pending refund ---------------
    if session["pending_refund"] is not None:
        answer = user_text.lower()
        if answer in YES:
            decision = True
        elif answer in NO:
            decision = False
        else:
            return jsonify({
                "session_id": session_id,
                "reply": "Lutfen iadeyi onaylamak icin 'yes', iptal icin 'no' yazin.",
                "awaiting_confirmation": True,
            })
        session["pending_refund"] = None
        return _run(session, session_id, refund_decision=decision)

    # --- Case 2: a normal new user message ------------------------------------
    if not user_text:
        return jsonify({"session_id": session_id, "reply": "", "awaiting_confirmation": False})

    session["messages"].append({"role": "user", "content": user_text})
    return _run(session, session_id, refund_decision=None)


def _run(session, session_id, refund_decision):
    """Drive run_agent_web; translate a pause into an in-chat confirmation prompt."""
    try:
        reply, messages = run_agent_web(session["messages"], refund_decision=refund_decision)
        session["messages"] = messages
        return jsonify({
            "session_id": session_id,
            "reply": reply,
            "awaiting_confirmation": False,
        })
    except ConfirmationRequired as exc:
        # The loop paused: a small refund needs the user's go-ahead. We did NOT append the
        # refund's assistant turn, so session["messages"] is still a valid, resumable history.
        args = exc.refund_args
        session["pending_refund"] = args
        prompt = (
            f"{args.get('amount')} TL tutarinda iade ({args.get('order_id')}) "
            f"onayliyor musunuz? (yes/no)"
        )
        return jsonify({
            "session_id": session_id,
            "reply": prompt,
            "awaiting_confirmation": True,
        })


if __name__ == "__main__":
    # Port 5050, not 5000: on macOS port 5000 is taken by the AirPlay Receiver.
    app.run(debug=True, port=5050)
