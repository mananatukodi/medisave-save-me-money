import "package:flutter_riverpod/flutter_riverpod.dart";

import "../../config/app_config.dart";
import "api_client.dart";

/// Manual override for tests.
final apiClientProvider = Provider<ApiClient>((ref) {
  return ApiClient(baseUrl: AppConfig.apiBaseUrl);
});
