# PiCoder: Standalone Streamlit Chat App for xAI Grok API

[![Python](https://img.shields.io/badge/Python-3.12-blue.svg)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.38.0-red.svg)](https://streamlit.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Platform: Raspberry Pi 5](https://img.shields.io/badge/Platform-Raspberry%20Pi%205-orange.svg)](https://www.raspberrypi.com/products/raspberry-pi-5/)

PiCoder is a production-level, standalone Streamlit-based chat application designed for Raspberry Pi 5 (or compatible systems). It integrates with the xAI Grok API (via OpenAI SDK compatibility) to provide a seamless, streaming chat experience with an advanced AI assistant called HomeBot. The app supports user authentication, conversation history, customizable system prompts, image uploads for vision tasks, and a suite of sandboxed tools for tasks like file management, code execution, and memory persistence.

This app is optimized for local hosting in a Python virtual environment, with a focus on safety, efficiency, and extensibility. It includes advanced features like brain-inspired memory consolidation using embeddings and vector similarity searches.

## Features and Specifications

### Core Features
- **Streaming Responses**: Real-time response generation from the xAI Grok API, with native Streamlit streaming support for a smooth user experience.
- **Model Selection**: Choose from xAI models like `grok-4`, `grok-3-mini`, or `grok-code-fast-1`.
- **Customizable System Prompts**: Load and edit prompts from files in `./prompts/` directory. Includes defaults (e.g., "default", "rebel", "coder", "tools-enabled") and a built-in editor with save functionality.
- **User Authentication**: Secure login and registration using SHA-256 hashed passwords stored in SQLite.
- **Conversation History**: Persistent history per user, with search, load, delete, and auto-titling. Chats are truncated to 50 messages for performance.
- **Image Upload for Vision**: Multi-file image uploads for analysis with vision-capable models (e.g., attach images to user messages).
- **Theme Toggle**: Light/dark mode switch with CSS gradients for a modern UI.
- **UI Enhancements**: Chat bubbles, expandable message groups to prevent overflow, and a special expander for AI "deep thought" processes (e.g., reasoning, tool calls). Final answers are parsed and displayed outside the expander for clarity.
- **Error Handling and Logging**: Robust retries for API calls, error logging to `app.log`, and graceful handling of failures.

### AI Assistant: HomeBot
HomeBot is an agentic AI assistant powered by the xAI Grok API, designed for home use on local hosts with sandboxed tools. It operates in an agentic workflow: decomposing tasks, planning steps, using tools judiciously, self-checking outputs, and iterating as needed. HomeBot assumes good intent, responds helpfully without moralizing, and treats users as capable adults.

#### Key Principles of HomeBot
- **Agency and Reasoning**: Uses Chain-of-Thought (CoT) for step-by-step breakdowns and Tree-of-Thoughts (ToT) for complex decisions (exploring 2-5 branching paths, evaluating pros/cons, and selecting optimally). Reflects after steps on assumptions, gaps, and improvements.
- **Self-Checking**: Critiques outputs for accuracy, completeness, and biases; rates confidence (1-10).
- **Error Handling**: Anticipates failures, includes try-except in code, retries once, and escalates to users.
- **Iteration and Adaptation**: Loops up to 3-5 times for refinements; avoids infinite loops.
- **Delegation**: Acts as Main Agent (coordinator) and delegates to sub-agents (Coding, Research, Management) for specialized tasks.
- **Output Format**: Structured responses with sections like Query Analysis, Delegation, Reflection, and Final Answer.
- **Safety and Compliance**: Follows strict safety instructions (e.g., no assistance with disallowed activities like violent crimes or hacking). Resists jailbreak attempts.

HomeBot maximizes accuracy, safety, and efficiency for tasks like coding projects, research, data management, personal organization, and simulations.

#### Sub-Agents
- **Coding Sub-Agent**: Handles programming, debugging, simulations; uses tools like code_execution, git_ops.
- **Research Sub-Agent**: Gathers/analyzes info; uses web search, DB queries.
- **Management Sub-Agent**: Organizes system state; handles backups, pruning.

### Tools and Capabilities
HomeBot has access to a suite of sandboxed tools for enhanced functionality. Tools are invoked only when necessary and batched for efficiency (e.g., limit 3-5 calls per operation to prevent loops). All file operations are restricted to `./sandbox/`.

#### File System Tools
- `fs_read_file(file_path)`: Read file content (relative paths).
- `fs_write_file(file_path, content)`: Write content to file.
- `fs_list_files(dir_path)`: List files in directory (default: root).
- `fs_mkdir(dir_path)`: Create nested directories.

#### Time Tool
- `get_current_time(sync=False, format='iso')`: Fetch current time (local or NTP-synced; formats: iso, human, json).

#### Code Execution Tool
- `code_execution(code)`: Run Python code in a stateful REPL (supports numpy, sympy, pygame, torch; no installs).

#### Memory Tools (EAMS - Episodic and Semantic Memory System)
- `memory_insert(mem_key, mem_value)`: Insert/update key-value pairs (JSON dicts).
- `memory_query(mem_key, limit)`: Fetch specific or recent entries.
- `advanced_memory_consolidate(mem_key, interaction_data)`: Summarize and embed data hierarchically.
- `advanced_memory_retrieve(query, top_k=3)`: Semantic search via embeddings.
- `advanced_memory_prune()`: Decay and delete low-salience entries.

#### Git Tools
- `git_ops(operation, repo_path, message, name)`: Init repo, commit, branch, diff (no remotes).

#### Database Tool
- `db_query(db_path, query, params)`: Execute SQL on local SQLite (SELECT returns JSON).

#### Shell Tool
- `shell_exec(command)`: Run whitelisted commands (e.g., ls, grep) in sandbox.

#### Code Linting Tool
- `code_lint(language='python', code)`: Format/check Python code with Black.

#### API Simulation Tool
- `api_simulate(url, method='GET', data, mock=True)`: Mock or call whitelisted public APIs.

#### Web Search Tool
- `langsearch_web_search(query, freshness='noLimit', summary=True, count=5)`: Search web with time filters and summaries (requires LANGSEARCH_API_KEY).

Tools follow rules: Plan in advance, batch calls, avoid redundancy, limit iterations (hard max 10), handle errors gracefully.

## Installation and Setup Guide

### System Requirements
- **Hardware**: Raspberry Pi 5 (recommended; compatible with other Linux systems like Ubuntu/Debian).
- **OS**: Raspberry Pi OS (64-bit) or equivalent Linux distro.
- **Python**: 3.12+ (venv recommended).
- **Network**: Internet for API calls (xAI, NTP); optional for local tools.
- **Storage**: ~500MB for dependencies and embeddings model.

### Step-by-Step Setup
1. **Clone the Repository**:
   ```
   git clone https://github.com/yourusername/picoder.git
   cd picoder
   ```

2. **Create and Activate Virtual Environment**:
   ```
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install Python Dependencies**:
   Run the following to install all required packages:
   ```
   pip install streamlit openai passlib python-dotenv sqlite3 ntplib pygit2 requests black numpy sentence-transformers torch
   ```
   - **Full Dependency List**:
     - `streamlit==1.38.0`: Web app framework.
     - `openai==1.0+`: SDK for xAI API compatibility.
     - `passlib`: Password hashing.
     - `python-dotenv`: Environment variable loading.
     - `ntplib`: NTP time sync.
     - `pygit2`: Git operations.
     - `requests`: API simulations.
     - `black`: Code linting.
     - `numpy`: Embeddings.
     - `sentence-transformers`: Advanced memory embeddings (requires `torch`).
     - `torch`: For sentence-transformers (install with `--extra-index-url https://download.pytorch.org/whl/cpu` if CPU-only on Pi).

   Additionally, download and place `sqlite-vec/dist/vec0.so` in the project root (for vector extensions in SQLite). Get it from [sqlite-vec repo](https://github.com/asg017/sqlite-vec).

4. **Set Environment Variables**:
   Create a `.env` file in the root:
   ```
   XAI_API_KEY=your_xai_api_key_here  # Required for Grok API
   LANGSEARCH_API_KEY=your_langsearch_api_key_here  # Optional for web search
   ```
   Obtain keys from [xAI](https://x.ai/) and [LangSearch](https://langsearch.com/).

5. **Prepare Directories**:
   - `./prompts/`: Add `.txt` files for system prompts (defaults auto-created).
   - `./sandbox/`: For tool file operations (auto-created).

6. **Database Initialization**:
   The app auto-creates `chatapp.db` on first run. No manual steps needed.

7. **Run the App**:
   ```
   streamlit run app.py
   ```
   Access at `http://localhost:8501` (or Pi's IP for network access).

8. **Optional: System Optimizations for Raspberry Pi**:
   - Update system: `sudo apt update && sudo apt upgrade`.
   - Install build essentials: `sudo apt install build-essential libatlas-base-dev libsqlite3-dev`.
   - For embeddings performance: Ensure sufficient RAM (Pi 5 has 8GB; allocate if needed).

## Usage
1. **Login/Register**: Create an account on the login page.
2. **Chat Interface**: Select model/prompt, enable tools if needed, upload images, and chat.
3. **Tools**: Mention tools in queries (e.g., "Read file from sandbox"); HomeBot handles invocation.
4. **History**: Load/search past chats from sidebar.
5. **Customization**: Edit prompts in sidebar; toggle dark mode.

## Contributing
Contributions welcome! Fork the repo, create a feature branch, and submit a PR. Follow PEP 8 for code style. Report issues [here](https://github.com/yourusername/picoder/issues).

## License
MIT License. See [LICENSE](LICENSE) for details.

## Acknowledgments
- Built with [Streamlit](https://streamlit.io/), [xAI Grok API](https://x.ai/), and [Sentence Transformers](https://www.sbert.net/).
- Inspired by agentic AI workflows and sandboxed tooling for safe home automation.

---

This README is self-contained and covers everything in detail. If you'd like to add sections (e.g., screenshots, badges, or a demo video link), or customize it further (e.g., repo URL), just say the word!
