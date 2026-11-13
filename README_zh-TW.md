# RTX 4050 電腦統一補測

目標環境：AMD Ryzen 7 7840HS、8 核心／16 執行緒、安裝 RAM 32 GB、Python 3.12。
GPU 不用於本套 NumPy／Numba 模擬。以實際執行時記錄的 Python、套件版本與系統資訊為準。

## 開始
1. 解壓縮到新的資料夾，例如 Downloads\SAGM_GWO_4050_Rerun。
   不要覆蓋舊專案，也不要把舊 runs／results 複製進來。
2. 接上電源，關閉其他重運算程式，保持筆電散熱與電源模式一致。
3. 雙擊 RUN_ALL.cmd。首次會建立獨立 Python 環境並安裝依賴，需網路。
4. 出現 Compatibility, solver and provenance checks passed 後會開始驗證與補測。
5. 結束後提供 SAGM_GWO_4050_RESULTS.zip。

若只想先檢查環境，在此資料夾執行：
    powershell -NoProfile -ExecutionPolicy Bypass -File .\RUN_ALL.ps1 -CheckOnly

## 範圍
| 項目 | 次數與處理 |
|---|---|
| 主套件 | 36 設定 × 30 seeds = 1,080 次，全部重新執行 |
| 備轉、λ 掃描 | 各補 60 非基準案例；各自共 90 筆，重用這次新跑的 nominal 基準 |
| 消融計數器／RDA | 從本次主實驗的三組各 30 seeds 重新彙整 |
| OSI／ERB 開發檢查 | 3 設定 × seeds 101–103 = 9 次 |
| OSI 校準稽核 | seeds 101–110，僅檢核，不改寫任何設定 |
| BR／PA | 30 seeds，每組 720 時段；保留逐相 P/Q/|S| 輸出 |
| IEEE 33 計時 | 使用本次序列主實驗，各 horizon 的 epoch runtime |
| IEEE 69 計時 | 10 seeds × 24 epochs |
| MISOCP／搜尋計時 | 33-bus Tp=1、33-bus Tp=5、69-bus Tp=5，各 8 epochs、30 SAGM seeds；SCIP 每 epoch 最多 1,800 秒 |
| CAPA／TPFR | 不包含，維持獨立封存 |

1,200 是主套件加敏感度的設定–seed 案例數，不含開發、校準、三相與 benchmark。
採序列執行，避免不同實驗競爭 CPU 污染計時；不預估整批完成時間。
新結果不一定與舊數值相同，須檢查差異後更新文稿，不能直接改硬體名稱沿用舊 runtime。
本流程不擴充消融設計，不新增 repair=False/local_search=True 的實驗。

## 中斷與續跑
已完成 seed 寫入 CSV 後才提交 JSON，且記錄 CSV SHA-256。
重新雙擊同一個 RUN_ALL.cmd 即續跑；完成的 seed 會顯示 SKIP。
中斷中的 seed 從頭重跑。MISOCP 以 epoch 續跑，失敗不會跳過後標成完成。
套件、程式、設定或硬體與首跑紀錄不同會停止，避免混入不同環境。
每分鐘 HEARTBEAT 只代表程序仍在運行，不表示該 seed 已完成。
同一資料夾有程序鎖；也請勿同時從另一個解壓資料夾啟動第二份補測。
執行期間會要求 Windows 暫不自動睡眠，結束後解除；不能阻止手動休眠、闔蓋或更新重開機。

## 驗證邊界
此啟動流程在交付端完成語法、規畫與單一 seed／checkpoint 測試。
Windows 啟動與完整 SCIP 批次必須在實驗機實跑，不能預先宣稱通過。
不要執行原 calibrate_osi.py：它會寫回設定；此新流程改用只讀校準稽核。
程式包不含既有 runs/results，確保補測結果來自這台電腦。

補測程式保留模擬核心不變。benchmark 額外輸出每個 SAGM seed 的搜尋時間與目標值；λ 分析改用既有的 Walsh-average Hodges–Lehmann 函式，修正原腳本把差值中位數標成 HL 的問題，與備轉分析一致。新統計值須重新核對。
