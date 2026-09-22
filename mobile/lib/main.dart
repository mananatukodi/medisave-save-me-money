import "package:flutter/material.dart";
import "package:flutter_localizations/flutter_localizations.dart";
import "package:flutter_riverpod/flutter_riverpod.dart";
import "package:intl/intl.dart";

import "l10n/app_localizations.dart";
import "routing/app_router.dart";
import "theme/brand.dart";

/// Supported languages in priority order (spec §28): Telugu first.
const supportedLocales = [Locale("te"), Locale("en"), Locale("hi")];

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const ProviderScope(child: MediSaveApp()));
}

class MediSaveApp extends ConsumerWidget {
  const MediSaveApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return MaterialApp.router(
      title: "MediSave AI",
      debugShowCheckedModeBanner: false,
      theme: buildMedisaveTheme(),
      routerConfig: appRouter,
      localizationsDelegates: const [
        AppLocalizations.delegate,
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      supportedLocales: supportedLocales,
      localeResolutionCallback: (deviceLocale, supported) {
        // Telugu-first default resolution.
        for (final locale in supported) {
          if (deviceLocale != null && deviceLocale.languageCode == locale.languageCode) {
            return locale;
          }
        }
        return const Locale("te");
      },
    );
  }
}

/// Simple helper so screens can read localizations and override language.
Locale deviceLocaleOrDefault() {
  final name = Intl.getCurrentLocale();
  if (name.startsWith("te")) return const Locale("te");
  if (name.startsWith("hi")) return const Locale("hi");
  return const Locale("en");
}

const brandScaffoldFallbackColor = Brand.background;
