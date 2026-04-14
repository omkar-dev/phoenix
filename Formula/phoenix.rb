class Phoenix < Formula
  desc "AI-powered GitHub Kanban board with one-click AI agent implementation"
  homepage "https://github.com/omkar-dev/homebrew-phoenix"
  license "AGPL-3.0-only"

  # Stable install — update url + sha256 each release:
  #   brew bump-formula-pr --url=... --sha256=...
  url "https://github.com/omkar-dev/homebrew-phoenix/archive/refs/tags/v5.0.0.tar.gz"
  sha256 "REPLACE_WITH_SHA256_OF_RELEASE_TARBALL"
  version "5.0.0"

  # Development install: brew install omkar-dev/phoenix/phoenix --HEAD
  head "https://github.com/omkar-dev/homebrew-phoenix.git", branch: "main"

  depends_on "git"
  depends_on "node"
  depends_on "python@3.12"

  def install
    python3 = Formula["python@3.12"].opt_bin/"python3"
    venv     = libexec/"venv"

    # ── Python agent ──────────────────────────────────────────────────────────
    system python3, "-m", "venv", venv
    system venv/"bin/pip", "install", "--no-cache-dir", "--upgrade", "pip"
    system venv/"bin/pip", "install", "--no-cache-dir", buildpath/"agent"

    # Shim scripts so the virtualenv binaries appear on PATH
    %w[phoenix-agent phoenix-semantic].each do |cmd|
      (bin/cmd).write_env_script(
        venv/"bin"/cmd,
        PATH: "#{venv}/bin:#{ENV["PATH"]}",
      )
    end

    # ── Astro frontend ────────────────────────────────────────────────────────
    # Build the static site; PUBLIC_* env vars default to localhost so the
    # pre-built frontend talks to the locally-running services.
    # Homebrew sets CWD to buildpath during install, so no --prefix needed.
    system "npm", "ci"
    system "npm", "run", "build"
    (pkgshare/"dist").install Dir["dist/*"]

    # ── pnx launcher ─────────────────────────────────────────────────────────
    # Single command that starts agent + semantic + a static file server for
    # the pre-built frontend.  Reads credentials from the environment; prompts
    # the user if required variables are missing.
    dist_dir = pkgshare/"dist"
    (bin/"pnx").write <<~BASH
      #!/usr/bin/env bash
      set -euo pipefail

      # ── Credentials check ─────────────────────────────────────────────────
      _check_var() {
        local name="$1" prompt="$2"
        if [[ -z "${!name:-}" ]]; then
          echo "  $name is not set."
          read -r -p "  Enter your $prompt: " val
          export "$name=$val"
        fi
      }

      echo "Phoenix v5 — starting services"

      _check_var GITHUB_TOKEN    "GitHub Personal Access Token (repo scope)"
      _check_var ANTHROPIC_API_KEY "Anthropic API key"

      # ── Port configuration ────────────────────────────────────────────────
      AGENT_PORT="${AGENT_PORT:-8001}"
      SEMANTIC_PORT="${SEMANTIC_PORT:-3001}"
      FRONTEND_PORT="${FRONTEND_PORT:-4321}"
      DIST="#{dist_dir}"

      # ── Start services ────────────────────────────────────────────────────
      pids=()
      cleanup() {
        echo ""
        echo "Shutting down…"
        for p in "${pids[@]}"; do kill "$p" 2>/dev/null || true; done
        wait 2>/dev/null || true
        echo "All services stopped."
      }
      trap cleanup INT TERM EXIT

      phoenix-agent --port "$AGENT_PORT" &
      pids+=($!)

      phoenix-semantic --port "$SEMANTIC_PORT" &
      pids+=($!)

      #{Formula["python@3.12"].opt_bin/"python3"} -m http.server "$FRONTEND_PORT" --directory "$DIST" \
        >/dev/null 2>&1 &

      for i in $(seq 1 60); do
        if curl -sf "http://localhost:$AGENT_PORT/health" >/dev/null 2>&1; then
          break
        fi
        if (( i % 10 == 0 )); then
          echo "  Still waiting for agent (${i}s)…"
        fi
        sleep 1
      done

      echo ""
      echo "  Frontend  → http://localhost:$FRONTEND_PORT"
      echo "  Agent     → http://localhost:$AGENT_PORT"
      echo "  Semantic  → http://localhost:$SEMANTIC_PORT"
      echo ""
      echo "  Press Ctrl+C to stop all services."
      echo ""

      # macOS: open browser automatically
      if command -v open &>/dev/null; then
        open "http://localhost:$FRONTEND_PORT" 2>/dev/null || true
      fi

      wait
    BASH
    chmod 0755, bin/"pnx"
  end

  def caveats
    <<~EOS
      Before running Phoenix, export your credentials:

        export GITHUB_TOKEN="your-github-pat"       # repo + pull_request:write scope
        export ANTHROPIC_API_KEY="your-api-key"     # or set per-agent in the UI

      Then start all services with:

        pnx

      The board opens at http://localhost:4321.
      Agent API runs on port 8001; semantic service on port 3001.

      To override ports:

        AGENT_PORT=9001 FRONTEND_PORT=9321 pnx

      Agent data (DB + git clones) is stored in ~/.pnx/.
    EOS
  end

  test do
    # Verify the Python entry points are wired correctly.
    assert_match "usage", shell_output("#{bin}/phoenix-agent --help 2>&1", 0)
    assert_match "usage", shell_output("#{bin}/phoenix-semantic --help 2>&1", 0)
  end
end
