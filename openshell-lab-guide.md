# Providing Secure Runtimes for AI Agents with NVIDIA OpenShell

Autonomous AI agents are increasingly expected to read and write files, call external APIs, install packages, and interact with language models on their own, often over long-running sessions with little human supervision. This autonomy is exactly what makes agents useful, but it also means a compromised, misconfigured, or simply overly capable agent can leak credentials, exfiltrate data, or take unintended actions on the host system. Telling an agent "don't do that" in a prompt is persuasion, not enforcement — a sufficiently motivated or confused agent can still try.

NVIDIA OpenShell addresses this problem by moving security controls out of the agent's reach and into the environment around it. Every agent runs inside an isolated sandbox governed by a declarative YAML policy that is enforced at the infrastructure and kernel level, not by the agent's own behavior. Policies are organized into four domains:

- **Filesystem** — which paths the agent may read or write, enforced with kernel-level isolation and locked in at sandbox creation.
- **Network** — which outbound destinations the agent may reach, denied by default and hot-reloadable at runtime.
- **Process** — which binaries the agent may execute, also locked in at sandbox creation.
- **Inference** — which LLM backend serves the agent's model calls, with credentials swapped at the routing layer so the agent never sees the real API key.

Because these controls sit outside the agent's process boundary, the agent cannot negotiate with them, override them, or leak a credential it was never given, even if it is compromised. In this lab, you will create sandboxes, apply and modify policies, wire up a real agent to a local model, and see how OpenShell can inject credentials into outbound requests without ever exposing them to the agent itself.

## Index of this lab

- Introduction to OpenShell
- Experiment with a real agent
- Credentials injection

## Introduction to OpenShell

In this section we create a sandbox, access its terminal, and test OpenShell's core filesystem, network, and process controls.

Open a terminal and go to the `oshell/intro` directory:

```bash
cd /home/demouser/Desktop/oshell/intro
```

Openshell management is done with the Openshell CLI. Let's create our first sandbox:

```bash
openshell sandbox create --name intro
```

This creates a sandbox from the base template and drops you directly into its terminal. A sandbox is the runtime where agents will run. Openshell supports 4 different "compute engines" to create sandboxes on top of: Docker, Podman, Kubernetes and MicroVM. In this lab we are going to use Docker. In practice this means that Openshell creates a container, starts a "supervisor" which is then tasked with creating a child process for the sandbox.

After creation, click the "**+"** symbol at the top-left of the terminal application to open a second terminal session. We will use this tab to run commands against the host, outside the sandbox. For example, you can list the sandboxes that currently exist:

```bash
openshell sandbox list
```

The `get` command shows you a detailed description of the sandbox, including its status, policy, and configuration:

```bash
openshell sandbox get intro
```

You can also inspect logs at the sandbox level. There is an optional `--since` flag to show only the most recent logs (for example, `--since 5m`):

```bash
openshell logs intro
```

You can also inspect the underlying container and its logs directly. These can be useful for lower-level troubleshooting. Notice how the container image came from `ghcr.io` (GitHub Container Registry) and corresponds to the OpenShell base image:

```bash
docker ps
docker logs <container ID or name>
```

Go back to the sandbox terminal and perform a few filesystem actions. First check the present working directory and attempt to create an empty file called "test"

```bash
pwd
touch test
```

The sandbox has write access to the "sandbox/" folder. So, we can show the contents of the folder to verify the file was indeed created.
```bash
ls
```

In contrast, the policy sets the "bin/" directory as read-only so the following file creation should fail. 
```bash
touch /bin/test
```

By default, a sandbox gets read-write access only to the current active workspace directory and temporary session folders. The rest of the host filesystem is either entirely inaccessible or restricted to strict read-only access. System binaries (such as those in `/bin/`) and host configuration layers cannot be modified under the default policy — this is why the last command above fails.

One important detail to remember: **filesystem and process boundaries are locked in permanently at sandbox creation**. They cannot be loosened or tightened by applying a new policy later; a sandbox with those boundaries in place must be recreated to change them.

From a networking perspective, every outbound connection attempt is blocked by default. Unlike the filesystem, however, **network policy can be hot-reloaded** into a running sandbox without recreating it — you'll see this in action shortly.

For now, let's delete this sandbox and instead attach a policy explicitly during creation. In the sandbox terminal, exit the sandbox:

```bash
exit
```

Now delete the sandbox.
```bash
openshell sandbox delete intro
```

Let's examine the policy file with the `less` command. It will open the policy in the terminal; you can scroll up and down with the cursor keys, and press `q` when you are done to return to the terminal:

```bash
less policy.yaml
```

The policy grants filesystem access to certain folders. It also opens network egress access to `api.github.com/zen` — a test URL that returns a random sentence, useful for confirming outbound access is working. Notice how the `binaries` section explicitly names the application (`python3`) that is allowed to reach that URL; any other binary attempting the same request will be denied.

Let's re-create the `intro` sandbox, this time applying the policy at creation time:

```bash
openshell sandbox create --name intro --policy ./policy.yaml
```

Move to the second terminal so we can run a few commands against the host. For example, use `get` again to examine the sandbox and confirm the policy was applied:

```bash
openshell sandbox get intro
```

Now we are going to run a Python script inside the sandbox that automates a few tests for us. Let's first examine the script in the host terminal:

```bash
less test.py
```

As you can see, it includes both filesystem tests and network policy tests.

Let's upload this script to the sandbox:

```bash
openshell sandbox upload intro test.py /sandbox/test.py
```

Now switch to the sandbox terminal and confirm the file is there:

```bash
ls -l
```

Let's run it:

```bash
python3 test.py
```

It fails. The script uses the `requests` library to reach out over the network, but `requests` is not installed. Let's install it with Python's standard package manager, `pip`:

```bash
pip install requests
```

The installation fails five times and then gives up. Why? Check the sandbox logs in the host terminal to find out:

```bash
openshell logs intro
```

`pip` is trying to reach `pypi.org:443`, the largest public repository of Python packages. Since our policy only allows egress to `api.github.com/zen` via `python3`, `pip`'s request is denied — the sandbox is doing exactly what it was told.

We're going to change the policy to allow access to PyPI. Recall that network policy can be updated on a running sandbox without recreating it. In the same folder there is a second policy file, `devpolicy.yaml`:

```bash
less devpolicy.yaml
```

Apply `devpolicy.yaml`. Notice how OpenShell keeps track of the policy's version as you update it:

```bash
openshell policy set intro --policy devpolicy.yaml --wait
```

This illustrates a common real-world pattern: you may not want a production agent to have open access to a package repository like PyPI, since that would let it install arbitrary code on its own. Instead, you can maintain a looser "development" policy to configure and provision the sandbox, and then swap in a stricter "production" policy before the agent starts doing real work — all without rebuilding the sandbox.

Now return to the sandbox terminal; you should be able to install the `requests` library:

```bash
pip install requests
```

With the library installed, the script should now run successfully. Run it again and verify the results are what you expected:

```bash
python3 test.py
```

This time the script runs and successfully reaches the `api.github.com/zen` URL. Let's try reaching it again, but this time using the `curl` command instead of the Python script:

```bash
curl https://api.github.com/zen
```

It fails. Why? Recall that the `binaries` section of the policy explicitly allows `python3` to reach `api.github.com/zen`. `curl` is a different binary, so the exact same URL is blocked when requested through it — network policy in OpenShell is enforced per binary, not just per destination.

Exit the sandbox terminal:

```bash
exit
```

## Experiment with a Real Agent

So far we have logged into the sandbox terminal and run commands manually. This has been useful for getting familiar with OpenShell and understanding how its policies behave, but in the real world we want a more automated workflow — and we haven't used a model yet. In this section, we'll work with a small, real agent that calls into a language model.

As a first step, change directory to `fullagent` in the two terminals you already have open:

```bash
$ cd /home/demouser/Desktop/oshell/fullagent
```

This environment has been pre-configured with Ollama, a tool that makes it very easy to run models locally. Run the following command to check which models are installed:

```bash
ollama ls
```

You should see a "granite" model with 1 billion parameters. Despite its small size, this model is well suited to tool use and instruction following. We have compiled a version of Granite that is deliberately restricted to a 4K-token context window to keep it small and fast for this lab.

One thing Ollama does not provide out of the box is the ability to require an API key to authenticate callers — it's designed to run on a local machine, where that isn't usually a concern. We want to demonstrate how the OpenShell proxy can inject sensitive information, like an API key, into outbound requests so that the agent inside the sandbox is never aware of the real secret.

To add key-based authentication on top of Ollama, we have deployed another tool called LiteLLM which acts as a proxy. You can inspect configuration file that was used to start LiteLLM:

```bash
cat /home/demouser/Desktop/oshell/litellm-config.yaml
```

Notice how it points at Ollama, which listens on port `11434`, and how it enforces key-based authentication via a master key, `topsecret123`. You can verify it is running:

```bash
ps -ef | grep litellm
```

Confirm that LiteLLM is routing requests to the Granite model in Ollama on port `4000`. The first request might take a few seconds to respond while the model loads into memory. Use `curl` to check that everything is working:

```bash
curl http://0.0.0.0:4000/v1/chat/completions \
  -H "Authorization: Bearer topsecret123" \
  -H "Content-Type: application/json" \
  -d '{"model": "granite", "messages": [{"role": "user", "content": "Hello!"}]}'
```

If you run a second request without the key, it should fail and complain that no API key was supplied:

```bash
$ curl http://0.0.0.0:4000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "granite", "messages": [{"role": "user", "content": "Hello!"}]}'
```

**A brief note on OpenShell providers:** in OpenShell, a *provider* is a named credential bundle — an API key, token, or other secret — that OpenShell manages and injects into a sandbox on its behalf. Instead of an agent holding a real secret directly, the agent's code refers only to the provider by name; OpenShell substitutes the actual credential when the request actually leaves the sandbox. This means a compromised or curious agent can never read out a credential it was never handed in the first place.

You'll also notice the `--config OPENAI_BASE_URL=http://host.openshell.internal:4000/v1` flag below, rather than a literal host IP address or `localhost`. `host.openshell.internal` is a special hostname that the OpenShell gateway resolves to "the host machine, as seen through the gateway." Routing through this name — instead of the sandbox's own idea of the host's real address — ensures that traffic destined for the host always passes through OpenShell's policy engine and, for inference traffic, its privacy router, rather than taking a shortcut straight to the host network. It also means the sandbox's network policy doesn't need to be aware of the host's actual IP, which can change between environments.

```bash
openshell provider create --name litellm-granite --type openai --credential API_KEY=topsecret123 --config OPENAI_BASE_URL=http://host.openshell.internal:4000/v1
openshell provider list
openshell provider get litellm-granite
```

**A brief note on OpenShell inference:** the `inference` domain is a special case of routing dedicated to LLM traffic. Rather than treating a model endpoint like any other network destination, OpenShell lets you bind a specific provider and model as the sandbox's managed inference backend. Calls the agent makes to its local, generic-looking model endpoint are transparently routed by the privacy router to that backend, with the provider's real credential injected at the gateway — the agent's own code never sees `topsecret123`. Like network policy, the inference binding is hot-reloadable, so you can point a sandbox at a different backend without recreating it.

```bash
openshell inference set --provider litellm-granite --model granite --no-verify
openshell inference get
```

This time we are going to create the sandbox by pointing at a Dockerfile instead of the base template. Examine the Dockerfile:

```bash
less Dockerfile
```

As you can see in the Dockerfile, the contents of the `sandbox` folder will be copied into the sandbox image. Take a look at the `sandbox` folder:

```bash
ls sandbox/
```

Now examine the app that implements the agent. Notice that the agent has access to three tools for operating on the filesystem and scraping websites, and that the app exposes two routes: an API for chat completions and a simple web UI:

```bash
less sandbox/app.py
```

In a production deployment, it might make more sense to run the GUI outside the sandbox and have it call the API endpoint inside the sandbox over the network. For convenience in this lab, we have kept both the GUI and the API inside the sandbox.

Let's quickly examine the policy:

```bash
less policy.yaml
```

Now let's deploy the sandbox — this may take around 30 seconds. The `.` after `--from` is important as it tells the openshell CLI where to locate the Dockerfile:

```bash
openshell sandbox create --name fullagent --policy ./policy.yaml --from . -- python3 app.py
```

Now connect to the sandbox.

```bash
openshell sandbox connect fullagent
```
Once inside the sandbox terminal, send a test request against its chat API. Notice how the request doesn't include the key that LiteLLM implements. Openshell is intercepting the request and injecting it before sending it to LiteLLM:
```bash
curl -X POST http://127.0.0.1:5000/api/chat -H "Content-Type: application/json" -d '{"message": "Hello!"}'
```

Let's exit the sandbox terminal:

```bash
exit
```

So far we have confirmed the managed inference endpoint can be reached from *inside* the sandbox. Now let's learn how the agent itself can be reached from *outside* the sandbox.

**A brief note on OpenShell services:** while filesystem, network, and process policy govern what the sandbox is allowed to reach *out* to, "services" govern the opposite direction — what is allowed to reach *in*. Exposing a service publishes a port from inside the sandbox so that it becomes reachable from the host (and, depending on configuration, the wider network), giving you a controlled ingress path into the agent without disabling any of the sandbox's isolation guarantees.

```bash
openshell service expose fullagent 5000
openshell service list
```

At this point the sandbox should reachable from the host, so we can test the agent through a browser. Open Firefox and perform the following steps:

- Open the exposed URL in a web browser.
- Try writing and reading back a file in an allowed path — for example: "Add 7+5 and put the result in a new file called test.txt inside the /sandbox directory".
- Try reading from a read-only location: "Read file /etc/hosts and tell me the internal IP address of docker".
- Test the web-scraping tool. Wikipedia is allowed by policy. Be careful, the URL is case-sensitive: "Summarize this webpage [https://en.wikipedia.org/wiki/Australia](https://en.wikipedia.org/wiki/Australia)".
- Verify that policy blocks other sites: "Summarize this webpage [https://docs.ollama.com/quickstart](https://docs.ollama.com/quickstart)".

You can inspect the agent's logs:

```bash
openshell logs fullagent | tail
```

You can press `CTRL + C` to exit the log stream.

In this lab we built the sandbox's container image by pointing at a folder containing a Dockerfile. In production, organizations will more often want to deploy a sandbox from an existing container image already sitting in a registry — likely built automatically by a CI/CD pipeline. The `--from` flag supports this directly. In the example below, we create a sandbox from an image published on Docker Hub. You can inspect the image's page here: [https://hub.docker.com/r/cermegno/oshelltest](https://hub.docker.com/r/cermegno/oshelltest)

```bash
openshell sandbox create --name registrytest --from cermegno/oshelltest:v1.0
```

It pulled the image and created the sandbox. Let's exit the sandbox terminal:

```bash
exit
```

You can inspect the sandbox:

```bash
openshell sandbox get registrytest
```

## Credentials Injection

In this section we'll see that the same mechanism used to hide the inference endpoint's credentials from the sandbox can be used for *any* external site — not just for LLM inference. This act of injecting credentials on the agent's behalf is accomplished with providers.

**Providers vs. Providers V2:** the provider mechanism you used earlier (creating the `litellm-granite` provider) is the original, "v1" model — a named credential is created once and then referenced directly when you create a sandbox or set up inference. It has no concept of lifecycle beyond creation and deletion. **Providers V2** builds on this with full lifecycle management: reusable, versioned *profiles* that describe a credential integration (including a network policy fragment), which can be validated (`lint`), imported into a shared catalog, instantiated as named providers, and — critically — **attached to or detached from a running sandbox on demand**. V1 providers are essentially fixed at sandbox creation time; V2 providers can be added to or removed from a live sandbox without recreating it, with the provider's network policy merged into the sandbox's existing policy automatically.

Providers v2 turns providers from credential records into profile-backed access bundles. A provider profile describes the credentials, endpoints, binaries and policy rules. Use Providers v2 when you want provider-owned policy rules to travel with provider credentials. For example, a GitHub provider can describe both GITHUB_TOKEN and the GitHub API endpoints that a sandbox needs, so users do not have to copy the same network policy into every sandbox. We'll enable and use V2 in this section.

Let's navigate to the `creds` folder which contains the files for this lab. Paste the following command in both terminals:

```bash
cd /home/demouser/Desktop/oshell/creds/
```

Examine `policy.yaml`:

```bash
less policy.yaml
```

Let's create a sandbox with this policy:

```bash
openshell sandbox create --name credtest --policy ./policy.yaml
```

Now let's enable Providers V2. After running the command below, you'll be asked to confirm with (`y/n)` — type `y`:

```bash
openshell settings set --global --key providers_v2_enabled --value true
```

Now we'll create a provider profile. As noted above, the V2 toolset adds lifecycle management on top of simple credential creation. Examine the profile definition:

```bash
less httpbin-profile.yaml
```

We can "lint" it to check the integrity of the profile file before importing:

```bash
openshell provider profile lint -f httpbin-profile.yaml
```

Let's import the profile:

```bash
openshell provider profile import -f httpbin-profile.yaml
```

Confirm it has been created by listing all profiles. You'll find it in the "Other" category, near the top. The rest are built-in profile types:

```bash
openshell provider list-profiles
```

Now we can create a provider of the profile type we just defined. From a security standpoint, it's best practice to read the credential value from an environment variable rather than typing it on the command line. So, first define `API_KEY` as an environment variable on the host, then create the provider. Notice how OpenShell reads `API_KEY` from the environment via the `--credential` flag:

```bash
export API_KEY=secret456
openshell provider create --name httpbin-demo --type httpbin-profile --credential API_KEY
```

You can double-check the provider exists. Notice its type matches the profile we created earlier:

```bash
openshell provider list
openshell provider get httpbin-demo
```

Finally, attach the provider to the sandbox:

```bash
openshell sandbox provider attach credtest httpbin-demo
```

This shows all providers currently attached to the sandbox:

```bash
openshell sandbox provider list credtest
```

If you `get` the sandbox now, you'll see that the httpbin network policy fragment has been merged into the sandbox's existing network policy. Before enabling Providers v2, the only way of defining network policies was through policy files, but now there is a network policy section associated to the provider, so they need to be merged. Notice how OpenShell prefixed the merged entry with an underscore (`_`) to distinguish it from the sandbox's own native policy:

```bash
openshell sandbox get credtest
```

Finally, let's connect to the sandbox and check whether it can see the credential. Open a terminal session into the sandbox:

```bash
openshell sandbox connect credtest
```

Inside the sandbox session, check whether the environment variable exists. Notice that it holds a placeholder value rather than the real credential:

```bash
echo $API_KEY
```

We can now proceed to confirm that the OpenShell proxy is intercepting the outgoing request and injecting the real credential into the headers. The httpbingo.org is a popular testing site amongst developers. It simply echoes back the details of whatever request you send it, which makes it great for testing:

```bash
$ curl -sS -H "Authorization: Bearer $API_KEY" https://httpbingo.org/headers
```

The output should show the `Authorization` header containing the real injected key, `secret456` — even though as we saw, the sandbox itself only ever held a placeholder value. This is the same substitution mechanism you saw earlier with the LiteLLM inference provider, applied here to an arbitrary external API.

## Recap

Over the course of this lab, you worked through the core building blocks of NVIDIA OpenShell:

- **Sandboxes** give each agent an isolated runtime with its own filesystem, process, and network boundaries, created either from a base template, a Dockerfile, or an existing registry image.
- **Filesystem and process policy** are locked in at sandbox creation and cannot be loosened later — you saw this when the sandbox could read/write only its workspace, and when `curl` was blocked while `python3` was allowed under the same network rule.
- **Network policy** is denied by default but can be hot-reloaded into a running sandbox, as you did when switching from `policy.yaml` to `devpolicy.yaml` to unblock PyPI access for development.
- **Providers** let OpenShell inject real credentials into outbound requests — for both managed inference (the LiteLLM/Granite setup, resolved through `host.openshell.internal`) and arbitrary external APIs (the httpbin example) — without ever exposing the real secret to the agent inside the sandbox.
- **Inference routing** treats LLM traffic as a first-class, hot-reloadable policy domain, separate from generic network egress.
- **Services** open a controlled ingress path into a sandbox, which you used to expose the full agent's web UI and chat API to a browser outside the sandbox.
- **Providers V2** extends the basic provider model with reusable, lintable profiles and the ability to attach or detach credentials from a live sandbox, merging their network policy in automatically.

Together, these controls let you give an agent broad functional capability — reading files, calling tools, invoking models, reaching external APIs — while keeping every one of those actions constrained by policy that lives outside the agent's own control, and fully auditable through `openshell logs`.

&nbsp;