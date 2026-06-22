#!/bin/bash
# 毎日12:55にMacを自動起動/スリープ解除する設定
# 一度だけ実行すればOK（sudo必要）

echo "=== 午後スロット自動起動設定 ==="
echo ""
echo "毎日 12:55 にMacがスリープから自動復帰するよう設定します。"
echo ""

# 毎日12:55に起動（月〜日）
sudo pmset repeat wakeorpoweron MTWRFSU 12:55:00

if [ $? -eq 0 ]; then
    echo "✅ 設定完了！毎日 12:55 にMacが自動起動します。"
    echo ""
    echo "現在の設定確認:"
    pmset -g sched
else
    echo "❌ エラー：sudo権限が必要です"
    echo "   sudo bash setup_afternoon_wake.sh  で実行してください"
fi
