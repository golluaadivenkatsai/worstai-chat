# 🤖 VersatileAI — 22-Agent Verification & Identity Swarm

An autonomous multi-agent verification and identity platform built with the theme of **[VersatileAI](https://versatile-ai-delta.vercel.app/)** and our **AI-Native Device Identity Architecture**.

---

## 🌐 Live URLs

- **Local Web Browser (PC):** [http://localhost:3000](http://localhost:3000)
- **Mobile Smartphone (Same Wi-Fi):** [http://192.168.1.109:3000](http://192.168.1.109:3000)

---

## ⚡ The 22 Specialized Agents in the Swarm

### 🛡️ Group 1: Security & Identity Enclave (6 Agents)
1. **Orchestrator Agent**: Decomposes tasks into concurrent execution streams and manages dependencies.
2. **Identity & DID Agent**: Issues sovereign W3C `did:agent:...` decentralized identifiers and Ed25519 keys.
3. **Titan Sandbox Agent**: Enforces hardware isolation boundaries (Titan M2 / Secure Enclave).
4. **SQLCipher Encryptor**: Manages on-device AES-256 encrypted database vaults.
5. **OAuth & Handshake Agent**: Generates pairwise tokens for apps (Spotify, Uber) with zero email exposure.
6. **Privacy Auditor Agent**: Strips network telemetry, trackers, and fingerprinting vectors.

### 📱 Group 2: Device HAL & Ecosystem Services (8 Agents)
7. **Action Dispatch Agent**: Replaces legacy email inboxes with direct machine-to-machine action packets.
8. **Long-Term Memory Agent**: Manages episodic memory facts, user profile details, and semantic recall.
9. **Checkpoint & Thread Agent**: Serializes conversation checkpoints and ensures zero state loss across restarts.
10. **Travel & Transit Agent**: Parses flight tickets, boarding passes, and auto-syncs device calendar.
11. **Finance & Transaction Agent**: Authorizes biometric payment requests without exposing credit card details.
12. **Commerce & Package Agent**: Tracks delivery statuses, order fulfillments, and purchase receipts.
13. **Biometrics & Health Agent**: Monitors device sensor telemetry with local biometric consent gates.
14. **Mobile HAL & Kernel Agent**: Hooks into the Android OS framework layer and system services.

### 🧠 Group 3: Reasoning, Code & Verification (8 Agents)
15. **Deep Research Agent**: Synthesizes documentation from academic and technical standards.
16. **Code & Tool Builder**: Writes verified, production-grade Python scripts with native tool decorators.
17. **Local NPU Scheduler**: Dynamically distributes model inference across CPU, GPU, and on-device NPU.
18. **Consensus Arbiter Agent**: Resolves divergence among agents and calculates consensus confidence.
19. **Verification & Fact-Check**: Detects hallucinations and audits reasoning against ground truth.
20. **Red-Team Critic Agent**: Probes the system for vulnerabilities, data leaks, and edge-case exploits.
21. **Synthesis & Summary Agent**: Compiles actionable, production-ready consensus reports.
22. **Voice & Interaction Agent**: Formats responses for natural acoustic speech synthesis.

---

## 🚀 How to Run the Server

```powershell
cd C:\Users\DELL\.gemini\antigravity-ide\scratch\versatile_ai_swarm
python server.py
```
Open **[http://localhost:3000](http://localhost:3000)** in your browser.
