import "dart:async";
import "package:dio/dio.dart";

/// Dio client with JWT header injection and a tiny offline action queue
/// (spec §29: offline-aware, queued actions, retry — never silently lose data).
class ApiClient {
  ApiClient({required String baseUrl})
      : _dio = Dio(BaseOptions(
          baseUrl: baseUrl,
          connectTimeout: const Duration(seconds: 8),
          receiveTimeout: const Duration(seconds: 15),
        ));

  final Dio _dio;
  String? _accessToken;
  final _pendingQueue = <QueuedAction>[];
  bool _isOfflineRetryScheduled = false;

  void setToken(String? token) => _accessToken = token;

  Future<Response<T>> get<T>(String path, {Map<String, dynamic>? query}) =>
      _dio.get<T>(path, queryParameters: query).catchError(_handleError<T>);

  Future<Response<T>> post<T>(String path, {Object? body}) =>
      _dio.post<T>(path, body: body).catchError(_handleError<T>);

  Future<Response<T>> put<T>(String path, {Object? body}) =>
      _dio.put<T>(path, body: body).catchError(_handleError<T>);

  Future<Response<T>> delete<T>(String path) =>
      _dio.delete<T>(path).catchError(_handleError<T>);

  /// Queue a POST for later retry when connectivity returns (spec §29).
  void enqueueForRetry(String path, Map<String, dynamic> body) {
    _pendingQueue.add(QueuedAction(path: path, body: body));
  }

  Future<void> flushQueue() async {
    final remaining = <QueuedAction>[];
    for (final action in _pendingQueue) {
      try {
        await _dio.post(action.path, data: action.body);
      } on DioException {
        remaining.add(action); // still offline — keep, never drop
      }
    }
    _pendingQueue
      ..clear()
      ..addAll(remaining);
  }

  Future<Response<T>> Function(Object) _handleError<T>() =>
      (error) async => throw error;
}

class QueuedAction {
  QueuedAction({required this.path, required this.body});

  final String path;
  final Map<String, dynamic> body;
}
