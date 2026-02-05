# Azure Deployment Tool

這是一個基於 PyQt6 構建的桌面應用程式，旨在簡化將本地專案部署到 Azure VM (或任何 Linux SSH 伺服器) 的流程。
專為 Python/Docker 專案設計，支援一鍵部署、自動與 Git 整合、以及遠端 Docker Compose 管理。

## 🎯 主要功能 (Features)

*   **圖形化介面 (GUI)**: 直覺的操作介面，無需手動輸入繁瑣的 SSH 指令。
*   **一鍵部署 (One-Click Deploy)**: 自動執行「備份 -> 上傳 -> 停止服務 -> 解壓縮 -> 啟動服務」完整流程。
*   **多環境管理 (Profile Management)**: 支援儲存多組連線設定 (如 Gray, Tech, Prod)，方便快速切換。
*   **Git 整合**:
    *   自動列出 Git Tags 以選擇特定版本打包。
    *   支援使用 "Current Workspace" 打包當前開發中的程式碼 (含 .env)。
*   **智慧服務偵測 (Smart Detection)**:
    *   自動偵測遠端運行的 Docker 服務目錄。
    *   自動列出遠端的 `docker-compose.yml` 檔案供選擇。
*   **自訂腳本 (Custom Scripts)**: 
    *   支援指定 `.sh` 腳本來執行服務的 Start/Stop (取代預設的 docker-compose 指令)，增加部署彈性。
*   **遠端備份**: 部署前自動備份遠端目錄，防止意外。
*   **即時 Console**: 視窗內直接顯示遠端指令執行結果與進度條。

## 🛠️ 安裝需求 (Prerequisites)

*   **Python 3.10+** (建議)
*   本地端已安裝 Git
*   遠端伺服器需支援 SSH (並建議擁有 sudo 權限)

### 安裝依賴 (Install Dependencies)

```bash
pip install -r requirements.txt
```

主要使用套件:
*   `PyQt6`: GUI 框架
*   `paramiko`: SSH 連線
*   `GitPython`: Git 操作

## 🚀 使用方法 (Usage)

### 1. 啟動程式

執行根目錄下的 `run.bat` (Windows) 或直接執行 python script:

```bash
python main.py
```

### 2. 連線設定 (Connection & Source)

1.  **Profile**: 選擇或輸入一個新設定檔名稱 (如 `Gray Env`)。
2.  **Host / Port / User**: 輸入遠端伺服器資訊。
3.  **Password**: 輸入 SSH 密碼 (若需執行 sudo 指令，此為必要)。
4.  **Key File**: (選填) 若使用 Key Pair 登入請選擇私鑰檔案。
5.  **Repository Path**: 選擇本地專案資料夾。
6.  **Git Tag**: 點擊右側 `↻` 刷新，選擇要部署的版本 (或選 Current Workspace)。
7.  **Pack Name**: 設定打包檔名 (自動產生)。
8.  **Save Config**: 設定完成後記得存檔。

### 3. 部署設定 (Deployment Config)

1.  **Remote Base**: 檔案上傳的基礎目錄 (例如 `/home/user/deploy`).
2.  **Target Service**: 
    *   輸入目標服務在遠端的目錄。
    *   點擊 **Auto Detect** 讓工具自動尋找。
3.  **Custom Scripts (進階選項)**:
    *   若不使用 Docker Compose，可指定 `.sh` 腳本來停止 (`Stop Script`) 或啟動 (`Start Script`) 服務。
    *   **Auto Detect** 也會自動尋找目錄下符合 `*down.sh` 或 `*up.sh` 的腳本。

### 4. 執行部署 (Actions)

*   **One-Click Deploy**: 推薦使用。自動跑完所有流程。
*   **個別按鈕**:
    *   `Upload`: 僅上傳打包檔。
    *   `Stop Service`: 停止運作中的容器 (或執行 Stop Script)。
    *   `Extract`: 解壓縮檔案。
    *   `Start Service`: 啟動容器 (或執行 Start Script)。

## 📝 Troubleshooting

*   **Permission Denied**: 
    *   確保 SSH 使用者有 sudo 權限。
    *   程式會嘗試使用 `sudo -S` 並自動帶入密碼，請確保密碼正確。
*   **找不到 Docker Compose**:
    *   請確認 `Target Service` 路徑正確。
    *   使用 **Auto Detect** 確認遠端檔案列表。

## 📂 專案結構

*   `src/`: 原始碼目錄
    *   `git_manager.py`: Git 操作封裝
    *   `ssh_manager.py`: SSH/SFTP 連線封裝
    *   `file_manager.py`: 檔案壓縮處理
    *   `main_window.py`: PyQt6 主視窗邏輯
*   `config.json`: 設定檔 (自動產生)
*   `main.py`: 程式入口
