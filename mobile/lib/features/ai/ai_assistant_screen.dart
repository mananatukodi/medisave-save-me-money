import "package:flutter/material.dart";
import "package:flutter_riverpod/flutter_riverpod.dart";

import "../../core/network/api_provider.dart";
import "../../l10n/app_localizations.dart";
import "../../theme/brand.dart";

/// AI Health Assistant chat screen (spec §10, §11).
///
/// The backend enforces the AI_ACCESS consent gate and the safety pipeline;
/// this screen renders the structured response and navigation actions.
class AiAssistantScreen extends ConsumerStatefulWidget {
  const AiAssistantScreen({super.key});

  @override
  ConsumerState<AiAssistantScreen> createState() => _AiAssistantScreenState();
}

class _AiMessage {
  _AiMessage({required this.text, required this.isUser, this.disclaimer, this.urgency});

  final String text;
  final bool isUser;
  final String? disclaimer;
  final String? urgency;
}

class _AiAssistantScreenState extends ConsumerState<AiAssistantScreen> {
  final _controller = TextEditingController();
  final _messages = <_AiMessage>[];
  String? _sessionId;
  bool _busy = false;
  String? _error;

  Future<void> _send() async {
    final text = _controller.text.trim();
    if (text.isEmpty || _busy) return;
    setState(() {
      _busy = true;
      _error = null;
      _messages.add(_AiMessage(text: text, isUser: true));
      _controller.clear();
    });
    try {
      final api = ref.read(apiClientProvider);
      final resp = await api.post<Map<String, dynamic>>(
        "/api/v1/ai/chat",
        body: {
          "message": text,
          "language": "te", // Telugu-first default (spec §28)
          if (_sessionId != null) "session_id": _sessionId,
        },
      );
      final data = resp.data ?? {};
      _sessionId = data["session_id"] as String?;
      final navs = (data["navigation"] as List?) ?? const [];
      final navText = navs
          .map((n) => "→ ${n["label_te"] ?? n["label_en"]}")
          .join("\n");
      setState(() {
        _messages.add(_AiMessage(
          text: navText.isEmpty
              ? (data["message"] as String? ?? "")
              : "${data["message"]}\n$navText",
          isUser: false,
          disclaimer: data["disclaimer"] as String?,
          urgency: data["urgency"] as String?,
        ));
      });
    } catch (err) {
      setState(() {
        _error = err.toString().contains("403")
            ? "AI_ACCESS consent required — open Settings → Consent Management."
            : "Request failed. Check connection and try again.";
      });
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context)!;
    return Scaffold(
      appBar: AppBar(title: Text(l10n.aiAssistant)),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 8, 12, 0),
            child: Text(l10n.aiPlaceholderNote,
                style: const TextStyle(fontSize: 12, color: Brand.darkText)),
          ),
          if (_error != null)
            Padding(
              padding: const EdgeInsets.all(12),
              child: Text(_error!, style: const TextStyle(color: Color(0xFFDC2626))),
            ),
          Expanded(
            child: ListView.builder(
              padding: const EdgeInsets.all(16),
              itemCount: _messages.length,
              itemBuilder: (context, index) {
                final m = _messages[index];
                final bubbleColor = m.isUser ? Brand.teal : Colors.white;
                final textColor = m.isUser ? Colors.white : Brand.darkText;
                return Align(
                  alignment: m.isUser ? Alignment.centerRight : Alignment.centerLeft,
                  child: Container(
                    margin: const EdgeInsets.only(bottom: 8),
                    padding: const EdgeInsets.all(12),
                    constraints: const BoxConstraints(maxWidth: 300),
                    decoration: BoxDecoration(
                      color: bubbleColor,
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        if (m.urgency == "EMERGENCY")
                          const Padding(
                            padding: EdgeInsets.only(bottom: 6),
                            child: Text("🚨", style: TextStyle(fontSize: 20)),
                          ),
                        Text(m.text, style: TextStyle(color: textColor)),
                        if (m.disclaimer != null)
                          Padding(
                            padding: const EdgeInsets.only(top: 6),
                            child: Text(
                              m.disclaimer!,
                              style: const TextStyle(fontSize: 11, fontStyle: FontStyle.italic),
                            ),
                          ),
                      ],
                    ),
                  ),
                );
              },
            ),
          ),
          SafeArea(
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: Row(
                children: [
                  Expanded(
                    child: TextField(
                      controller: _controller,
                      decoration: InputDecoration(hintText: l10n.askAi),
                      onSubmitted: (_) => _send(),
                    ),
                  ),
                  const SizedBox(width: 8),
                  IconButton.filled(
                    onPressed: _busy ? null : _send,
                    icon: _busy
                        ? const SizedBox(
                            width: 18, height: 18,
                            child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                          )
                        : const Icon(Icons.send),
                    tooltip: l10n.send,
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
