/// Whether [value] has the shape of an email address.
///
/// The check is deliberately small: no spaces, one `@`, text on both sides,
/// and a dot inside the domain. Clerk makes the final decision. The check
/// only stops obvious typos before a send uses up the rate limit.
bool isPlausibleEmailAddress(String value) {
  if (value.isEmpty || value.contains(RegExp(r"\s"))) {
    return false;
  }
  final parts = value.split("@");
  if (parts.length != 2 || parts.first.isEmpty) {
    return false;
  }
  final domain = parts.last;
  final dot = domain.indexOf(".");
  return dot > 0 && dot < domain.length - 1 && !domain.endsWith(".");
}
