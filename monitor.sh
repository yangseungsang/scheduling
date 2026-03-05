#!/bin/bash
# 에이전트 팀 모니터링 tmux 레이아웃

SESSION="scheduling-agents"
DIR="/Users/yangseungmin/Projects/scheduling"

# 기존 세션 종료
tmux kill-session -t "$SESSION" 2>/dev/null

# 새 세션 생성 (detached)
tmux new-session -d -s "$SESSION" -x 220 -y 50

# ── 레이아웃 ──────────────────────────────────────────
# [Pane 0: git log] [Pane 1: blueprint-dev]
# [Pane 2: template-dev] [Pane 3: flask server]
# [Pane 4: 파일 변경 감시]
# ─────────────────────────────────────────────────────

# Pane 0: git log (왼쪽 상단)
tmux send-keys -t "$SESSION:0" "echo '=== GIT 활동 (2초 갱신) ===' && watch -n 2 'git -C $DIR log --oneline --graph -15 2>/dev/null'" Enter

# Pane 1: blueprint-dev 진행 (오른쪽 상단)
tmux split-window -h -t "$SESSION:0"
tmux send-keys -t "$SESSION:0.1" "echo '=== BLUEPRINT-DEV 진행상황 ===' && watch -n 2 'ls -la $DIR/app/blueprints/tasks/ $DIR/app/blueprints/admin/ $DIR/app/blueprints/schedule/ 2>/dev/null'" Enter

# Pane 2: template-dev 진행 (왼쪽 하단)
tmux split-window -v -t "$SESSION:0.0"
tmux send-keys -t "$SESSION:0.2" "echo '=== TEMPLATE-DEV 진행상황 ===' && watch -n 2 'ls -la $DIR/app/templates/schedule/ $DIR/app/templates/tasks/ $DIR/app/templates/admin/ 2>/dev/null'" Enter

# Pane 3: Flask 앱 서버 (오른쪽 하단)
tmux split-window -v -t "$SESSION:0.1"
tmux send-keys -t "$SESSION:0.3" "cd $DIR && echo '=== FLASK 서버 (준비되면 Enter) ===' && echo 'python run.py 명령으로 서버 시작'" Enter

# 전체 파일 변경 감시 (하단 full-width)
tmux select-layout -t "$SESSION:0" tiled

# 세션에 attach
tmux attach-session -t "$SESSION"
