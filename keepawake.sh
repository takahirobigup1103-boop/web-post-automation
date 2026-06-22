#!/bin/bash
# 投稿スロット中にMacがスリープしないようにする（4時間）
# LaunchAgentから 6:55 / 12:55 / 19:55 に自動実行される
exec /usr/bin/caffeinate -it 14400
