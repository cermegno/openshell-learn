from flask import Flask, render_template, request, jsonify
import requests
from bs4 import BeautifulSoup
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent

app = Flask(__name__)

# Web Access Tool
@tool
def read_website(url: str) -> str:
    """Go to any specified URL/website, parse its text content, and return it safely."""
    try:
        if not url.startswith("http://") and not url.startswith("https://"):
            url = "https://" + url
            
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        response = requests.get(url, headers=headers, timeout=12)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, "html.parser")
        for script in soup(["script", "style"]):
            script.decompose()
            
        text = soup.get_text(separator="\n", strip=True)
        return text[:15000] # Safe truncation safeguard
    except requests.exceptions.Timeout:
        return f"Error: The request to {url} timed out. The website might be down or slow."
    except requests.exceptions.ConnectionError:
        return f"Error: Failed to connect to {url}. Please check if the URL is correct or valid."
    except requests.exceptions.HTTPError as e:
        return f"Error: HTTP failure accessing {url}. Status code: {e.response.status_code}"
    except Exception as e:
        return f"Error retrieving URL {url}: {str(e)}"

# Local File Read Tool
@tool
def read_file(file_path: str) -> str:
    """Read the contents of a local file from any path specified by the user."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        return content[:15000]
    except FileNotFoundError:
        return f"Error: The file at '{file_path}' could not be found. Please verify the path."
    except PermissionError:
        return f"Error: Permission denied when trying to read '{file_path}'."
    except Exception as e:
        return f"Error reading file '{file_path}': {str(e)}"

# Local File Write Tool
@tool
def write_file(file_path: str, content: str) -> str:
    """Write content to a local file at any path specified by the user."""
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Successfully wrote content to file: {file_path}"
    except PermissionError:
        return f"Error: Permission denied when attempting to write to '{file_path}'."
    except Exception as e:
        return f"Error writing file '{file_path}': {str(e)}"

tools = [read_website, read_file, write_file]

# Configure LangChain with local gemma-4-e2b model endpoint
model = ChatOpenAI(
    base_url="https://inference.local/v1",
    api_key="not-needed",
    model="granite",
    temperature=0
)

system_prompt = (
    "You are an advanced assistant with tools to browse any website URL, read local files, and write local files. "
    "Always rely on tools when requested. If a tool returns an error message, explain that gracefully to the user."
)

# Create the agent
agent = create_agent(
        model=model, 
        tools=tools, 
        system_prompt=system_prompt)

# Flask Routes
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.get_json()
    if not data or "message" not in data:
        return jsonify({"detail": "Missing 'message' in JSON payload"}), 400
    
    try:
        user_message = data["message"]
        print("about to query agent")
        result = agent.invoke({"messages": [{"role": "user", "content": user_message}]})
        print(result)
        final_response = result["messages"][-1].content
        return jsonify({"response": final_response})
    except Exception as e:
        return jsonify({"detail": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
