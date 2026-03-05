
import sys
import os
import json
import re
from datetime import datetime
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QLineEdit, QPushButton, QFileDialog, 
                             QTabWidget, QMessageBox, QGroupBox, QComboBox, QCheckBox, 
                             QListWidget, QAbstractItemView, QSizePolicy, QInputDialog, QProgressBar, QGridLayout,
                             QSplitter)
from PyQt6.QtCore import QThread, pyqtSignal, Qt

from src.ssh_manager import SSHManager
from src.git_manager import GitManager
from src.file_manager import FileManager
from src.ui.console_widget import ConsoleWidget

if getattr(sys, 'frozen', False):
    APP_PATH = os.path.dirname(sys.executable)
else:
    APP_PATH = os.path.dirname(os.path.abspath(__file__))
    APP_PATH = os.path.dirname(os.path.dirname(APP_PATH)) # Go up two levels from src/main_window.py to root

CONFIG_FILE = os.path.join(APP_PATH, "config.json")

class WorkerThread(QThread):
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int)
    command_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(bool, object)

    def __init__(self, task_func, *args, **kwargs):
        super().__init__()
        self.task_func = task_func
        self.args = args
        self.kwargs = kwargs

    def run(self):
        try:
            # We assume task_func might accept 'progress_callback' in kwargs 
            # but here we just run it. The task_func closure in MainWindow 
            # will capture self.progress_signal.emit if needed.
            success, message = self.task_func(*self.args, **self.kwargs)
            self.finished_signal.emit(success, message)
        except Exception as e:
            self.finished_signal.emit(False, str(e))

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Azure Deployment Tool")
        self.resize(1000, 700)
        
        # Managers
        self.ssh_manager = SSHManager()
        self.git_manager = GitManager()
        self.file_manager = FileManager()
        
        # Profile Init
        self.profiles = {}
        self.current_profile_name = "Default"
        
        self.config = self.load_config()

        # UI Components
        self.init_ui()
        self.load_ui_values()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        central_layout = QVBoxLayout(central_widget)
        central_layout.setContentsMargins(0, 0, 0, 0)
        
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        central_layout.addWidget(self.splitter)

        # Left Panel (Main Content)
        left_widget = QWidget()
        main_layout = QVBoxLayout(left_widget)

        # Tabs
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

        # Tab 1: Connection & Source
        self.setup_connection_tab()
        
        # Tab 2: Deployment
        self.setup_deployment_tab()

        # Console (Global)
        self.console = ConsoleWidget()
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        
        main_layout.addWidget(QLabel("Progress:"))
        main_layout.addWidget(self.progress_bar)

        # Console Output Header with History Toggle
        console_header_layout = QHBoxLayout()
        console_header_layout.addWidget(QLabel("Console Output:"))
        
        self.chk_show_history = QCheckBox("Show Command History")
        self.chk_show_history.toggled.connect(self.toggle_history_panel)
        console_header_layout.addWidget(self.chk_show_history)
        console_header_layout.addStretch()
        
        main_layout.addLayout(console_header_layout)
        main_layout.addWidget(self.console, stretch=1)
        
        self.splitter.addWidget(left_widget)

        # Right Panel (Command History)
        self.history_widget = QWidget()
        history_layout = QVBoxLayout(self.history_widget)
        
        history_title = QLabel("Command History")
        history_title.setStyleSheet("font-weight: bold;")
        history_layout.addWidget(history_title)
        
        self.list_history = QListWidget()
        self.list_history.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list_history.setWordWrap(True)
        history_layout.addWidget(self.list_history, stretch=1)
        
        btn_clear_history = QPushButton("Clear History")
        btn_clear_history.clicked.connect(self.list_history.clear)
        history_layout.addWidget(btn_clear_history)

        self.splitter.addWidget(self.history_widget)
        
        # Initial state: history hidden
        self.history_widget.setVisible(False)
        self.splitter.setSizes([800, 0])

    def toggle_history_panel(self, checked):
        self.history_widget.setVisible(checked)
        if checked:
            self.splitter.setSizes([700, 300]) # Example weights
        else:
            self.splitter.setSizes([1000, 0])

    def log_command(self, cmd_str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.list_history.addItem(f"[{timestamp}] {cmd_str}\n")
        self.list_history.scrollToBottom()

    def setup_connection_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Profile Management Group
        prof_group = QGroupBox("Profile Management")
        prof_layout = QHBoxLayout(prof_group)
        
        self.combo_profile = QComboBox()
        self.combo_profile.setEditable(True)
        self.combo_profile.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.combo_profile.addItems(list(self.profiles.keys()))
        self.combo_profile.setCurrentText(self.current_profile_name)
        self.combo_profile.activated.connect(self.on_profile_switch)
        
        btn_del_profile = QPushButton("Delete Profile")
        btn_del_profile.clicked.connect(self.delete_profile)
        
        prof_layout.addWidget(QLabel("Profile:"))
        prof_layout.addWidget(self.combo_profile, stretch=1)
        prof_layout.addWidget(btn_del_profile)
        
        layout.addWidget(prof_group)
        
        # Connection Settings Group
        conn_group = QGroupBox("SSH Connection")
        conn_layout = QVBoxLayout(conn_group)
        
        # Host/Port/User Row
        row1 = QHBoxLayout()
        self.input_host = QComboBox()
        self.input_host.setEditable(True)
        self.input_host.setPlaceholderText("Host IP")
        
        # Load hosts
        saved_hosts = self.config.get('saved_hosts', [])
        self.input_host.addItems(saved_hosts)
        
        self.input_port = QLineEdit("22")
        self.input_port.setPlaceholderText("Port")
        self.input_user = QLineEdit()
        self.input_user.setPlaceholderText("Username")
        row1.addWidget(QLabel("Host:"))
        row1.addWidget(self.input_host, stretch=1)
        row1.addWidget(QLabel("Port:"))
        row1.addWidget(self.input_port)
        row1.addWidget(QLabel("User:"))
        row1.addWidget(self.input_user)
        conn_layout.addLayout(row1)
        
        # Auth Row
        row2 = QHBoxLayout()
        self.input_key_path = QLineEdit()
        self.input_key_path.setPlaceholderText("Path to Private Key")
        btn_browse_key = QPushButton("Browse")
        btn_browse_key.clicked.connect(self.browse_key_file)
        
        self.input_password = QLineEdit()
        self.input_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_password.setPlaceholderText("Password (Optional if Key used)")
        
        row2.addWidget(QLabel("Key:"))
        row2.addWidget(self.input_key_path)
        row2.addWidget(btn_browse_key)
        row2.addWidget(QLabel("Or Password:"))
        row2.addWidget(self.input_password)
        conn_layout.addLayout(row2)
        
        conn_btn_layout = QHBoxLayout()
        btn_test_conn = QPushButton("Test Connection")
        btn_test_conn.clicked.connect(self.test_connection)
        btn_save_config = QPushButton("Save Config / Profile")
        btn_save_config.clicked.connect(self.save_config)
        conn_btn_layout.addWidget(btn_test_conn)
        conn_btn_layout.addWidget(btn_save_config)
        conn_layout.addLayout(conn_btn_layout)
        
        layout.addWidget(conn_group)

        # Source Preparation Group
        src_group = QGroupBox("Source Preparation")
        src_layout = QVBoxLayout(src_group)
        
        # Path Selection
        path_row = QHBoxLayout()
        self.input_repo_path = QLineEdit()
        self.input_repo_path.setPlaceholderText("Local Repository Path")
        btn_browse_repo = QPushButton("Browse")
        btn_browse_repo.clicked.connect(self.browse_repo_path)
        path_row.addWidget(QLabel("Repo:"))
        path_row.addWidget(self.input_repo_path)
        path_row.addWidget(btn_browse_repo)
        src_layout.addLayout(path_row)
        
        # Git & File Actions
        action_row = QHBoxLayout()
        btn_git_pull = QPushButton("Git Pull")
        btn_git_pull.clicked.connect(self.run_git_pull)
        
        # Tag Selection
        self.combo_tags = QComboBox()
        self.combo_tags.addItem("Current Workspace")
        self.combo_tags.setMinimumWidth(150)
        self.combo_tags.currentTextChanged.connect(self.update_pack_name)
        
        btn_refresh_tags = QPushButton("↻")
        btn_refresh_tags.setToolTip("Refresh Tags")
        btn_refresh_tags.clicked.connect(self.load_tags)
        
        self.input_pack_name = QLineEdit("deploy_package.tar.gz")
        self.input_pack_name.setPlaceholderText("Package Filename")
        
        btn_pack = QPushButton("Pack Files")
        btn_pack.clicked.connect(self.run_pack)
        
        action_row.addWidget(btn_git_pull)
        action_row.addWidget(QLabel("Ver:"))
        action_row.addWidget(self.combo_tags)
        action_row.addWidget(btn_refresh_tags)
        action_row.addWidget(QLabel("Name:"))
        action_row.addWidget(self.input_pack_name)
        action_row.addWidget(btn_pack)
        src_layout.addLayout(action_row)
        
        layout.addWidget(src_group)
        layout.addStretch()
        self.tabs.addTab(tab, "Connection & Source")

    def setup_deployment_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Settings
        deploy_group = QGroupBox("Deployment Config")
        d_layout = QVBoxLayout(deploy_group)
        
        # Row 1: Remote Upload Path (Base)
        row1 = QHBoxLayout()
        self.input_remote_path = QLineEdit("/tempdata")
        self.input_remote_path.setPlaceholderText("Remote Base Path")
        row1.addWidget(QLabel("Remote Base:"))
        row1.addWidget(self.input_remote_path)
        d_layout.addLayout(row1)

        # Row 2: Target Service Path (for stopping old service)
        row2 = QHBoxLayout()
        self.input_target_path = QLineEdit()
        self.input_target_path.setPlaceholderText("Path to OLD service (auto-detected)")
        
        self.combo_compose_file = QComboBox()
        self.combo_compose_file.setEditable(True)
        self.combo_compose_file.setFixedWidth(180)
        self.combo_compose_file.addItem("docker-compose.yml")
        self.combo_compose_file.setToolTip("Select or Type Compose Filename")
        
        btn_detect = QPushButton("Auto Detect")
        btn_detect.setToolTip("Find running service path & list YML files")
        btn_detect.clicked.connect(self.auto_detect_service)
        
        row2.addWidget(QLabel("Target Service:"))
        row2.addWidget(self.input_target_path)
        row2.addWidget(self.combo_compose_file)
        row2.addWidget(btn_detect)
        d_layout.addLayout(row2)
        
        layout.addWidget(deploy_group)
        
        # Custom Scripts Group
        script_group = QGroupBox("Custom Scripts (Advanced)")
        script_layout = QGridLayout(script_group)
        
        self.chk_stop_script = QCheckBox("Use Stop Script (Down):")
        self.combo_stop_script = QComboBox()
        self.combo_stop_script.setEditable(True)
        self.combo_stop_script.setPlaceholderText("Optional: Select .sh to run INSTEAD of 'docker-compose down'")
        self.combo_stop_script.setMinimumWidth(300)
        self.combo_stop_script.setEnabled(False)
        self.chk_stop_script.toggled.connect(self.combo_stop_script.setEnabled)
        
        self.chk_start_script = QCheckBox("Use Start Script (Up):")
        self.combo_start_script = QComboBox()
        self.combo_start_script.setEditable(True)
        self.combo_start_script.setPlaceholderText("Optional: Select .sh to run INSTEAD of 'docker-compose up'")
        self.combo_start_script.setMinimumWidth(300)
        self.combo_start_script.setEnabled(False)
        self.chk_start_script.toggled.connect(self.combo_start_script.setEnabled)

        script_layout.addWidget(self.chk_stop_script, 0, 0)
        script_layout.addWidget(self.combo_stop_script, 0, 1)
        script_layout.addWidget(self.chk_start_script, 1, 0)
        script_layout.addWidget(self.combo_start_script, 1, 1)
        
        layout.addWidget(script_group)
        
        # Actions
        act_group = QGroupBox("Actions")
        a_layout = QVBoxLayout(act_group)
        
        # Individual Steps
        steps_layout = QHBoxLayout()
        
        btn_backup = QPushButton("0. Backup")
        btn_backup.clicked.connect(self.run_backup_service)

        btn_upload = QPushButton("1. Upload")
        btn_upload.clicked.connect(self.run_upload)
        
        btn_stop = QPushButton("2. Stop Old")
        btn_stop.clicked.connect(self.run_stop_service)
        
        btn_extract = QPushButton("3. Extract New")
        btn_extract.clicked.connect(self.run_extract)

        btn_build = QPushButton("3.5 Build")
        btn_build.clicked.connect(self.run_build_image)

        btn_start = QPushButton("4. Start New")
        btn_start.clicked.connect(self.run_start_service)
        
        steps_layout.addWidget(btn_backup)
        steps_layout.addWidget(btn_upload)
        steps_layout.addWidget(btn_stop)
        steps_layout.addWidget(btn_extract)
        steps_layout.addWidget(btn_build)
        steps_layout.addWidget(btn_start)
        
        a_layout.addLayout(steps_layout)
        
        # Separator or Space
        a_layout.addSpacing(10)
        
        # One Click
        one_click_layout = QHBoxLayout()
        btn_one_click = QPushButton("One-Click Deploy")
        btn_one_click.clicked.connect(self.run_one_click_deploy)
        btn_one_click.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        
        # Style deployment buttons
        font = btn_one_click.font()
        font.setBold(True)
        btn_one_click.setFont(font)
        btn_one_click.setStyleSheet("background-color: #dcedc8; padding: 15px;")
        
        # Options for One Click
        self.chk_backup = QCheckBox("Backup Old Service")
        self.chk_backup.setChecked(True) # Default on? Or off. Let's say True for safety.
        self.chk_backup.setToolTip("Create a backup copy of the target directory before deploying")
        
        one_click_layout.addWidget(btn_one_click)
        one_click_layout.addWidget(self.chk_backup)
        
        a_layout.addLayout(one_click_layout)

        layout.addWidget(act_group)
        layout.addStretch()
        
        self.tabs.addTab(tab, "Deployment")

    # --- Utils & Logic ---

    def log(self, text):
        # Strip ANSI escape codes
        clean_text = re.sub(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', '', text)
        self.console.append_log(clean_text)

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    data = json.load(f)
                    
                # Check structure
                if 'profiles' in data:
                    self.profiles = data.get('profiles', {})
                    self.current_profile_name = data.get('current_profile', 'Default')
                else:
                    # Legacy migration
                    self.profiles = {'Default': data}
                    self.current_profile_name = 'Default'
                
                # Ensure current profile exists in dict
                if self.current_profile_name not in self.profiles:
                     self.profiles[self.current_profile_name] = {}
                     
                return self.profiles[self.current_profile_name]
            except:
                pass
        
        # Fallback
        self.profiles = {'Default': {}}
        self.current_profile_name = 'Default'
        return self.profiles['Default']

    
    def on_profile_switch(self):
        # Called when user selects an item from dropdown
        name = self.combo_profile.currentText()
        if name in self.profiles:
            self.current_profile_name = name
            self.config = self.profiles[name]
            self.load_ui_values()
            self.log(f"Switched to profile: {name}")

    def delete_profile(self):
        name = self.combo_profile.currentText()
        if name == "Default":
            QMessageBox.warning(self, "Error", "Cannot delete Default profile.")
            return
            
        confirm = QMessageBox.question(self, "Confirm Delete", f"Delete profile '{name}'?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if confirm == QMessageBox.StandardButton.Yes:
            if name in self.profiles:
                del self.profiles[name]
                
            self.current_profile_name = "Default"
            self.config = self.profiles["Default"]
            
            # Update UI
            self.combo_profile.removeItem(self.combo_profile.findText(name))
            self.combo_profile.setCurrentText("Default")
            self.load_ui_values()
            self.save_config_file()
            self.log(f"Profile '{name}' deleted.")

    def save_config_file(self):
        # Save entire profiles dict
        data = {
            "profiles": self.profiles,
            "current_profile": self.current_profile_name
        }
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            self.log(f"Error saving file: {e}")

    def save_config(self):
        # Determine profile name (User might have typed a new one)
        profile_name = self.combo_profile.currentText().strip()
        if not profile_name:
            profile_name = "Default"
            
        # If new profile
        if profile_name not in self.profiles:
            self.profiles[profile_name] = {}
            self.combo_profile.addItem(profile_name)
            self.log(f"Created new profile: {profile_name}")
            
        self.current_profile_name = profile_name
        self.config = self.profiles[profile_name]
        
        # Save values to current config
        current_host = self.input_host.currentText().strip()
        self.config['host'] = current_host 
        
        # Save host list
        saved = self.config.get('saved_hosts', [])
        if current_host and current_host not in saved:
            saved.append(current_host)
            self.config['saved_hosts'] = saved
            self.input_host.addItem(current_host)

        self.config['port'] = self.input_port.text()
        self.config['user'] = self.input_user.text()
        self.config['key_path'] = self.input_key_path.text()
        self.config['repo_path'] = self.input_repo_path.text()
        self.config['remote_path'] = self.input_remote_path.text()
        self.config['pack_name'] = self.input_pack_name.text()
        self.config['target_path'] = self.input_target_path.text()
        self.config['compose_file'] = self.combo_compose_file.currentText()
        self.config['backup_enabled'] = self.chk_backup.isChecked()
        self.config['stop_script'] = self.combo_stop_script.currentText()
        self.config['start_script'] = self.combo_start_script.currentText()
        
        self.save_config_file()
        self.log(f"Profile '{profile_name}' saved.")

    def load_ui_values(self):
        self.input_host.setEditText(self.config.get('host', ''))
        self.input_port.setText(self.config.get('port', '22'))
        self.input_user.setText(self.config.get('user', ''))
        self.input_key_path.setText(self.config.get('key_path', ''))
        self.input_repo_path.setText(self.config.get('repo_path', ''))
        self.input_remote_path.setText(self.config.get('remote_path', '/tempdata'))
        self.input_pack_name.setText(self.config.get('pack_name', 'deploy_package.tar.gz'))
        self.input_target_path.setText(self.config.get('target_path', ''))
        self.combo_compose_file.setEditText(self.config.get('compose_file', 'docker-compose.yml'))
        self.chk_backup.setChecked(self.config.get('backup_enabled', True))
        self.combo_stop_script.setEditText(self.config.get('stop_script', ''))
        self.combo_start_script.setEditText(self.config.get('start_script', ''))
        # Auto load tags if repo path exists
        if self.input_repo_path.text():
            self.load_tags()

    def browse_key_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Private Key")
        if path:
            self.input_key_path.setText(path)

    def browse_repo_path(self):
        path = QFileDialog.getExistingDirectory(self, "Select Repository")
        if path:
            self.input_repo_path.setText(path)
            self.load_tags()

    def load_tags(self):
        path = self.input_repo_path.text()
        if not path: return
        
        self.combo_tags.blockSignals(True) # Block signals to avoid double update during reload
        self.combo_tags.clear()
        self.combo_tags.addItem("Current Workspace")
        
        tags = self.git_manager.get_tags(path)
        if tags:
            self.combo_tags.addItems(tags)
            self.log(f"Loaded {len(tags)} tags from repo.")
        else:
            self.log("No tags found or not a valid git repo.")
            
        self.combo_tags.blockSignals(False)
        self.update_pack_name(self.combo_tags.currentText())

    def update_pack_name(self, tag_text):
        path = self.input_repo_path.text()
        if not path: return
        
        project_name = os.path.basename(path)
        safe_tag = tag_text
        
        if safe_tag == "Current Workspace":
            new_name = f"{project_name}.tar.gz"
        else:
            # Clean tag name simply to be safe for filename
            safe_tag = safe_tag.replace('/', '_').replace('\\', '_')
            new_name = f"{project_name}_{safe_tag}.tar.gz"
            
        self.input_pack_name.setText(new_name)

    # --- Async Actions ---
    
    def get_ssh_details(self):
        return (self.input_host.currentText().strip(), self.input_port.text(), 
                self.input_user.text(), self.input_password.text(), 
                self.input_key_path.text())

    def test_connection(self):
        host, port, user, pwd, key = self.get_ssh_details()
        self.log(f"Testing connection to {user}@{host}:{port}...")
        
        def task():
            return self.ssh_manager.connect(host, port, user, pwd, key)
            
        self.worker = WorkerThread(task)
        self.worker.finished_signal.connect(lambda s, m: self.log(f"Connection Result: {m}"))
        self.worker.start()

    def run_git_pull(self):
        path = self.input_repo_path.text()
        if not path:
            self.log("Please select a repository path.")
            return

        self.log(f"Running git pull in {path}...")
        
        def task():
            return self.git_manager.pull(path, output_callback=self.worker.log_signal.emit)
            
        self.worker = WorkerThread(task)
        self.worker.log_signal.connect(self.log)
        
        def on_git_finished(success, message):
            self.log(f"Git Pull Finished: {message}")
            if not success:
                QMessageBox.warning(self, "Git Pull Failed", 
                                    f"Git pull failed.\n\nError details:\n{message}\n\nPlease check your repository, network, or authentication (Token/Password).")
            else:
                # Refresh tags after pull as new tags might have arrived
                self.load_tags()

        self.worker.finished_signal.connect(on_git_finished)
        self.worker.start()

    def run_pack(self):
        path = self.input_repo_path.text()
        pack_name = self.input_pack_name.text()
        selected_tag = self.combo_tags.currentText()
        
        if not path or not pack_name:
            self.log("Please select repo path and define package name.")
            return
            
        if not pack_name.endswith('.tar.gz'):
            pack_name += '.tar.gz'
            self.input_pack_name.setText(pack_name)

        root_folder = pack_name.replace('.tar.gz', '')

        if selected_tag == "Current Workspace":
            self.log(f"Packing CURRENT WORKSPACE from {path} into {pack_name} (Folder: {root_folder})...")
            def task():
                files = self.file_manager.get_all_files(path)
                return self.file_manager.compress_files(path, files, pack_name, root_dir=root_folder, 
                                                      log_callback=self.worker.log_signal.emit,
                                                      progress_callback=self.worker.progress_signal.emit)
        else:
            self.log(f"Archiving TAG '{selected_tag}' from {path} into {pack_name} (Folder: {root_folder})...")
            def task():
                # Git archive doesn't support fine-grained file progress easily, but we can try. 
                # For now just log.
                return self.git_manager.archive_repo(path, selected_tag, pack_name, prefix=root_folder, output_callback=self.worker.log_signal.emit)

        self.worker = WorkerThread(task)
        self.worker.log_signal.connect(self.log)
        self.worker.progress_signal.connect(self.progress_bar.setValue)
        self.worker.finished_signal.connect(lambda s, m: self.log(f"Pack Result: {m}"))
        self.worker.start()

    def run_upload(self):
        host, port, user, pwd, key = self.get_ssh_details()
        local_pack = self.input_pack_name.text()
        remote_path = self.input_remote_path.text().rstrip('/') + '/' + local_pack
        
        self.log(f"Uploading {local_pack} to {remote_path}...")
        
        def task():
            # 1. Connect
            ok, msg = self.ssh_manager.connect(host, port, user, pwd, key)
            if not ok: return False, msg
            
            # 2. Upload
            def progress(transferred, total):
                if total > 0:
                    percent = int(transferred / total * 100)
                    self.worker.progress_signal.emit(percent)
                    # self.worker.log_signal.emit(f"Transferred: {transferred}/{total}") # Optional: distinct log

            return self.ssh_manager.upload_file(local_pack, remote_path, progress_callback=progress)
            
        self.worker = WorkerThread(task)
        self.worker.log_signal.connect(self.log)
        self.worker.progress_signal.connect(self.progress_bar.setValue)
        self.worker.finished_signal.connect(lambda s, m: self.log(f"Upload Result: {m}"))
        self.worker.start()

    def _get_common_paths(self):
        local_pack = self.input_pack_name.text()
        remote_base = self.input_remote_path.text().rstrip('/')
        root_folder = local_pack.replace('.tar.gz', '')
        
        # Path where the NEW service will be extracted and started
        start_target_dir = f"{remote_base}/{root_folder}"
        
        # Path where the OLD service is running (for stopping)
        # Default to user input, fallback to start_target_dir if empty (assuming overwrite same version)
        stop_target_dir = self.input_target_path.text().strip()
        if not stop_target_dir:
            stop_target_dir = start_target_dir
            
        compose_file = self.combo_compose_file.currentText().strip()
        if not compose_file: compose_file = "docker-compose.yml"
            
        return local_pack, remote_base, root_folder, start_target_dir, stop_target_dir, compose_file

    def auto_detect_service(self):
        path = self.input_repo_path.text()
        if not path:
            self.log("Please select a repository path first (to get project name).")
            return
            
        default_name = os.path.basename(path)
        saved_name = self.config.get('service_keyword', default_name)
        
        # Prompt user to confirm/edit keyword
        search_name, ok = QInputDialog.getText(self, "Service Detection", 
                                             "Enter Project Keyword for Docker Filter:", 
                                             text=saved_name)
        if not ok or not search_name.strip():
            self.log("Detection cancelled.")
            return
            
        search_name = search_name.strip()
        
        # Save for future use
        if search_name != self.config.get('service_keyword'):
            self.config['service_keyword'] = search_name
            self.save_config_file()
            
        host, port, user, pwd, key = self.get_ssh_details()
        search_path_fallback = self.input_remote_path.text().strip()
        
        self.log(f"Auto-detecting running service for keyword '{search_name}' (Fallback Path: {search_path_fallback or '~'})...")
        
        def task():
            ok, msg = self.ssh_manager.connect(host, port, user, pwd, key)
            if not ok: return False, msg
            
            # 1. Detect service
            found, result_data = self.ssh_manager.detect_running_service(search_name, search_path=search_path_fallback)
            
            if not found:
                 return False, result_data # error msg
            
            # Prepare data for all found targets
            full_results = []
            for path_result, detected_file in result_data:
                # 2. List YML files in detected path
                files_ok, files = self.ssh_manager.list_working_dir_files(path_result)
                if not files_ok: files = [] 
                
                # 3. List .sh files
                scripts_ok, scripts = self.ssh_manager.list_scripts(path_result)
                if not scripts_ok: scripts = []
                
                full_results.append((path_result, detected_file, files, scripts))
                
            return True, full_results
            
        def on_finished(success, result):
            if not success:
                self.log(f"Detection failed: {result}")
                QMessageBox.warning(self, "Detection Failed", f"Could not detect running service.\n{result}")
                return

            full_results = result
            if not full_results:
                return

            def apply_target(path_result, detected_file, files, scripts):
                self.input_target_path.setText(path_result)
                
                # --- YML Files ---
                self.combo_compose_file.clear()
                self.combo_compose_file.addItems(files)
                
                if detected_file and detected_file in files:
                    self.combo_compose_file.setCurrentText(detected_file)
                elif "docker-compose.yml" in files:
                    self.combo_compose_file.setCurrentText("docker-compose.yml")
                elif detected_file:
                    self.combo_compose_file.addItem(detected_file)
                    self.combo_compose_file.setCurrentText(detected_file)
                elif files:
                    self.combo_compose_file.setCurrentIndex(0)
                else:
                    self.combo_compose_file.addItem("docker-compose.yml")

                # --- Scripts ---
                self.combo_stop_script.clear()
                self.combo_start_script.clear()
                self.combo_stop_script.addItems(scripts)
                self.combo_start_script.addItems(scripts)
                
                # Auto-select scripts based on convention
                stop_match = next((s for s in scripts if 'down' in s.lower()), None)
                start_match = next((s for s in scripts if 'up' in s.lower()), None)
                
                if stop_match:
                    self.combo_stop_script.setCurrentText(stop_match)
                    self.chk_stop_script.setChecked(True)
                else:
                    self.combo_stop_script.setCurrentIndex(-1)
                    self.chk_stop_script.setChecked(False)

                if start_match:
                    self.combo_start_script.setCurrentText(start_match)
                    self.chk_start_script.setChecked(True)
                else:
                    self.combo_start_script.setCurrentIndex(-1)
                    self.chk_start_script.setChecked(False)

                self.log(f"Detected: {path_result}. Found {len(files)} config files, {len(scripts)} scripts.")
                
            if len(full_results) == 1:
                path_result, detected_file, files, scripts = full_results[0]
                apply_target(path_result, detected_file, files, scripts)
            else:
                items = [f"{item[0]} [{item[1]}]" for item in full_results]
                selected_item, ok = QInputDialog.getItem(self, "Select Service Path",
                                                         "Multiple services detected, please choose one:",
                                                         items, 0, False)
                if ok and selected_item:
                    idx = items.index(selected_item)
                    path_result, detected_file, files, scripts = full_results[idx]
                    apply_target(path_result, detected_file, files, scripts)
                else:
                    self.log("Service selection cancelled.")

        self.worker = WorkerThread(task)
        self.worker.log_signal.connect(self.log)
        self.worker.finished_signal.connect(on_finished)
        self.worker.start()

    def run_stop_service(self):
        host, port, user, pwd, key = self.get_ssh_details()
        _, _, _, _, stop_target_dir, compose_file = self._get_common_paths()
        
        if not stop_target_dir:
             self.log("Error: No target service path specified for stopping.")
             return

        stop_script = self.combo_stop_script.currentText().strip()
        use_script = self.chk_stop_script.isChecked()
        
        if use_script and stop_script:
             self.log(f"Stopping Service using SCRIPT: {stop_script} in {stop_target_dir}...")
        else:
             self.log(f"Stopping Service in {stop_target_dir} ({compose_file})...")
        
        def task():
            ok, msg = self.ssh_manager.connect(host, port, user, pwd, key)
            if not ok: return False, msg
            
            if use_script and stop_script:
                # Custom Script Execution
                cmd = f"cd {stop_target_dir} && sudo -S bash {stop_script}"
            else:
                # Standard Docker Compose
                # Use -f checks
                cmd = f"if [ -d {stop_target_dir} ]; then cd {stop_target_dir} && if [ -f {compose_file} ]; then docker compose -f {compose_file} down; else echo '{compose_file} not found in {stop_target_dir}'; fi; else echo 'Directory {stop_target_dir} not found'; fi"
            
            self.worker.command_signal.emit(cmd)
            return self.ssh_manager.execute_command(cmd, output_callback=self.worker.log_signal.emit, sudo_password=pwd)

        self.worker = WorkerThread(task)
        self.worker.log_signal.connect(self.log)
        self.worker.command_signal.connect(self.log_command)
        self.worker.finished_signal.connect(lambda s, m: self.log(f"Stop Service Finished: {m}"))
        self.worker.start()

    
    def run_backup_service(self):
        host, port, user, pwd, key = self.get_ssh_details()
        _, _, _, _, stop_target_dir, _ = self._get_common_paths()
        
        if not stop_target_dir:
            self.log("Error: No target service path specified for backup.")
            return

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log(f"Backing up {stop_target_dir} (Compression)...")
        
        def task():
            ok, msg = self.ssh_manager.connect(host, port, user, pwd, key)
            if not ok: return False, msg
            
            # Backup command: tar -czvf dir_bak_ts.tar.gz dir
            # Use sudo -S for permission
            cmd = f"if [ -d {stop_target_dir} ]; then sudo -S tar -czvf {stop_target_dir}_bak_{ts}.tar.gz {stop_target_dir}; echo 'Backup created at {stop_target_dir}_bak_{ts}.tar.gz'; else echo 'Directory {stop_target_dir} not found, nothing to backup'; fi"
            self.worker.command_signal.emit(cmd)
            return self.ssh_manager.execute_command(cmd, output_callback=self.worker.log_signal.emit, sudo_password=pwd)

        self.worker = WorkerThread(task)
        self.worker.log_signal.connect(self.log)
        self.worker.command_signal.connect(self.log_command)
        self.worker.finished_signal.connect(lambda s, m: self.log(f"Backup Result: {m}"))
        self.worker.start()

    def run_extract(self):
        host, port, user, pwd, key = self.get_ssh_details()
        local_pack, remote_base, _, _, _, _ = self._get_common_paths()
        
        self.log(f"Extracting {local_pack} in {remote_base}...")
        
        def task():
            ok, msg = self.ssh_manager.connect(host, port, user, pwd, key)
            if not ok: return False, msg
            
            # tar -xzvf [file] -C [dest] or cd [dest] && tar...
            cmd = f"cd {remote_base} && sudo -S tar --overwrite -xzvf {local_pack}"
            self.worker.command_signal.emit(cmd)
            return self.ssh_manager.execute_command(cmd, output_callback=self.worker.log_signal.emit, sudo_password=pwd)

        self.worker = WorkerThread(task)
        self.worker.log_signal.connect(self.log)
        self.worker.command_signal.connect(self.log_command)
        self.worker.finished_signal.connect(lambda s, m: self.log(f"Extraction Finished: {m}"))
        self.worker.start()

    def run_build_image(self):
        host, port, user, pwd, key = self.get_ssh_details()
        _, _, _, start_target_dir, _, compose_file = self._get_common_paths()
        
        self.log(f"Building Service in {start_target_dir} ({compose_file})...")
        
        def task():
            ok, msg = self.ssh_manager.connect(host, port, user, pwd, key)
            if not ok: return False, msg
            
            cmd = f"cd {start_target_dir} && if [ -f {compose_file} ]; then docker compose -f {compose_file} build; else echo 'Error: {compose_file} not found'; exit 1; fi"
            self.worker.command_signal.emit(cmd)
            return self.ssh_manager.execute_command(cmd, output_callback=self.worker.log_signal.emit, sudo_password=pwd)

        self.worker = WorkerThread(task)
        self.worker.log_signal.connect(self.log)
        self.worker.command_signal.connect(self.log_command)
        self.worker.finished_signal.connect(lambda s, m: self.log(f"Build Service Finished: {m}"))
        self.worker.start()

    def run_start_service(self):
        host, port, user, pwd, key = self.get_ssh_details()
        _, _, _, start_target_dir, _, compose_file = self._get_common_paths()
        
        start_script = self.combo_start_script.currentText().strip()
        use_script = self.chk_start_script.isChecked()
        
        if use_script and start_script:
             self.log(f"Starting Service using SCRIPT: {start_script} in {start_target_dir}...")
        else:
             self.log(f"Starting Service in {start_target_dir} ({compose_file})...")
        
        def task():
            ok, msg = self.ssh_manager.connect(host, port, user, pwd, key)
            if not ok: return False, msg
            
            if use_script and start_script:
                # Custom Script Execution
                cmd = f"cd {start_target_dir} && sudo -S bash {start_script}"
            else:
                cmd = f"cd {start_target_dir} && if [ -f {compose_file} ]; then docker compose -f {compose_file} up -d --build; else echo 'Error: {compose_file} not found'; exit 1; fi"
            self.worker.command_signal.emit(cmd)
            return self.ssh_manager.execute_command(cmd, output_callback=self.worker.log_signal.emit, sudo_password=pwd)

        self.worker = WorkerThread(task)
        self.worker.log_signal.connect(self.log)
        self.worker.command_signal.connect(self.log_command)
        self.worker.finished_signal.connect(lambda s, m: self.log(f"Start Service Finished: {m}"))
        self.worker.start()

    def run_one_click_deploy(self):
        host, port, user, pwd, key = self.get_ssh_details()
        local_repo = self.input_repo_path.text()
        local_pack, remote_base, root_folder, start_target_dir, stop_target_dir, compose_file = self._get_common_paths()
        remote_file_path = f"{remote_base}/{local_pack}"
        
        self.log("Starting One-Click Deployment...")
        
        def task():
            # 1. Pack
            self.worker.log_signal.emit("--- Step 1: Packing ---")
            
            selected_tag = self.combo_tags.currentText()
            if selected_tag == "Current Workspace":
                files = self.file_manager.get_all_files(local_repo)
                ok, msg = self.file_manager.compress_files(local_repo, files, local_pack, root_dir=root_folder, progress_callback=self.worker.log_signal.emit)
            else:
                 ok, msg = self.git_manager.archive_repo(local_repo, selected_tag, local_pack, prefix=root_folder, output_callback=self.worker.log_signal.emit)
                 
            if not ok: return False, f"Pack failed: {msg}"
            
            # 2. Connect
            self.worker.log_signal.emit("--- Step 2: Connecting ---")
            ok, msg = self.ssh_manager.connect(host, port, user, pwd, key)
            if not ok: return False, f"Connection failed: {msg}"
            
            # 3. Upload
            self.worker.log_signal.emit("--- Step 3: Uploading ---")
            ok, msg = self.ssh_manager.upload_file(local_pack, remote_file_path, progress_callback=lambda transferred, total: self.worker.log_signal.emit(f"Transferred: {transferred}/{total}"))
            if not ok: return False, f"Upload failed: {msg}"
            
            # 4. Commands (Combined for one-shot execution to ensure sequential dependency)
            self.worker.log_signal.emit("--- Step 4: Remote Commands ---")
            
            commands = []
            
            # Optional Backup
            if self.config.get('backup_enabled', True):
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                # Add backup command
                # We use remote date generally, but here we inject local time string for simplicity or use $(date)
                # Let's use $(date +%Y%m%d_%H%M%S) for remote consistency 
                backup_cmd = f"if [ -d {stop_target_dir} ]; then sudo -S tar -czvf {stop_target_dir}_bak_$(date +%Y%m%d_%H%M%S).tar.gz {stop_target_dir}; echo 'Backup created'; else echo 'No old service to backup'; fi"
                commands.append(backup_cmd)
            
            
            stop_script = self.combo_stop_script.currentText().strip()
            use_stop_script = self.chk_stop_script.isChecked()
            
            if use_stop_script and stop_script:
                stop_cmd = f"if [ -d {stop_target_dir} ]; then cd {stop_target_dir} && sudo -S bash {stop_script}; else echo 'Stop target dir not found, skipping down'; fi"
            else:
                stop_cmd = f"if [ -d {stop_target_dir} ]; then cd {stop_target_dir} && if [ -f {compose_file} ]; then docker-compose -f {compose_file} down; else echo 'No {compose_file} at stop target, skipping down'; fi; else echo 'Stop target dir not found, skipping down'; fi"

            start_script = self.combo_start_script.currentText().strip()
            use_start_script = self.chk_start_script.isChecked()
            
            if use_start_script and start_script:
                start_cmd = f"cd {start_target_dir} && sudo -S bash {start_script}"
            else:
                start_cmd = f"cd {start_target_dir} && if [ -f {compose_file} ]; then docker-compose -f {compose_file} up -d --build; else echo 'Error: {compose_file} not found'; exit 1; fi"

            commands.extend([
                stop_cmd,
                f"cd {remote_base}",
                f"sudo -S tar --overwrite -xzvf {local_pack}", 
                start_cmd
            ])
            
            full_cmd = " && ".join(commands)
            self.worker.log_signal.emit(f"Executing: {full_cmd}")
            
            self.worker.command_signal.emit(full_cmd)
            ok, msg = self.ssh_manager.execute_command(full_cmd, output_callback=self.worker.log_signal.emit, sudo_password=pwd)
            return ok, msg

        self.worker = WorkerThread(task)
        self.worker.log_signal.connect(self.log)
        self.worker.command_signal.connect(self.log_command)
        self.worker.finished_signal.connect(lambda s, m: self.log(f"One-Click Deploy Finished: {m}"))
        self.worker.start()
