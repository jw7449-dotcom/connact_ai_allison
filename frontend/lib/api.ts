const unavailableMessage =
  "The service is temporarily unavailable. Please retry shortly. / 服务暂时不可用，请稍后重试。";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly retryable = false,
    public readonly status?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  let response: Response;
  try {
    response = await fetch("/api" + path, {
      ...options,
      headers: {
        ...(options.body instanceof FormData
          ? {}
          : { "Content-Type": "application/json" }),
        ...options.headers,
      },
      cache: "no-store",
    });
  } catch (error) {
    if (options.signal?.aborted) throw error;
    throw new ApiError(
      "Unable to connect to the service. Please retry. / 无法连接服务，请重试。",
      true,
    );
  }
  if (
    response.status === 401 &&
    !path.startsWith("/auth/") &&
    typeof window !== "undefined"
  )
    window.dispatchEvent(new Event("connact-session-expired"));

  const retryable =
    response.status >= 500 || [408, 429].includes(response.status);
  let data: unknown;
  try {
    // Hosting gateways can return HTML (including HTTP 200 while waking up).
    // Never expose the browser's JSON parser exception as an application error.
    const body = await response.text();
    data = body ? JSON.parse(body) : undefined;
    if (data === undefined && response.status !== 204) throw new Error();
  } catch (error) {
    if (options.signal?.aborted) throw error;
    throw new ApiError(
      response.ok || retryable
        ? unavailableMessage
        : "The request could not be completed. Please retry. / 请求未能完成，请重试。",
      response.ok || retryable,
      response.status,
    );
  }
  if (!response.ok) {
    const detail =
      data && typeof data === "object" && "detail" in data
        ? data.detail
        : undefined;
    const validation = Array.isArray(detail)
      ? detail
          .filter(
            (item): item is { msg: string; loc: (string | number)[] } =>
              !!item && typeof item.msg === "string" && Array.isArray(item.loc),
          )
          .map((item) => `${item.loc.slice(1).join(".")}: ${item.msg}`)
          .join("; ")
      : "";
    throw new ApiError(
      typeof detail === "string"
        ? detail
        : validation ||
            (retryable
              ? unavailableMessage
              : "Request failed. Please retry. / 请求失败，请重试。"),
      retryable,
      response.status,
    );
  }
  return data as T;
}
export const post = <T>(path: string, data: unknown = {}) =>
  api<T>(path, { method: "POST", body: JSON.stringify(data) });
export const put = <T>(path: string, data: unknown) =>
  api<T>(path, { method: "PUT", body: JSON.stringify(data) });
export function errorText(e: unknown) {
  return e instanceof Error ? e.message : "Something went wrong. Please retry.";
}
