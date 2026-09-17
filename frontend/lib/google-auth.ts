const googleErrors: Record<string, string> = {
  google_cancelled:
    "Google sign-in was canceled. Please try again. / 已取消 Google 登录，请重试。",
  google_invalid_state:
    "This sign-in link has expired or belongs to another browser. Please try again. / 登录请求已失效，请重新登录。",
  google_expired:
    "This sign-in link has expired. Please try again. / 登录请求已过期，请重新登录。",
  google_invitation_required:
    "A valid invitation for this Google email is required. / 此 Google 邮箱需要有效的邀请码。",
  google_invitation_invalid:
    "This invitation is expired, fully used, or belongs to another email. / 邀请码已失效、名额已用完，或与 Google 邮箱不匹配。",
  google_invalid_identity:
    "Google identity could not be verified. Please sign in again. / 无法验证 Google 身份，请重新登录。",
  google_unavailable:
    "Google sign-in is temporarily unavailable. Please try again. / Google 登录暂时不可用，请重试。",
  google_identity_conflict:
    "This account is linked to a different Google identity. Please contact the administrator. / 此账号已绑定其他 Google 身份，请联系管理员。",
  google_link_required:
    "Sign in to your existing account before linking this Google account. Contact the administrator for help. / 请先登录原账号再绑定此 Google 账号；如无法登录，请联系管理员。",
  google_not_configured:
    "Google sign-in is awaiting server configuration. / Google 登录尚待服务端配置。",
  google_admin_link_session:
    "Your administrator session has changed or expired. Sign in again before linking Google. / 管理员会话已变更或过期，请重新登录后绑定 Google。",
  google_admin_link_email:
    "Choose the Google account that matches the email you entered. Use a Gmail or Google Workspace account. / 请选择与填写邮箱一致的 Gmail 或 Google Workspace 账号。",
};

export function googleErrorText(code: string) {
  return (
    googleErrors[code] ||
    "Google sign-in could not be completed. Please try again. / Google 登录未完成，请重试。"
  );
}

export function googleAuthorizationUrl(value: string) {
  const destination = new URL(value);
  if (
    destination.origin !== "https://accounts.google.com" ||
    destination.username ||
    destination.password
  )
    throw new Error("The service returned an invalid Google sign-in URL.");
  return destination.href;
}
