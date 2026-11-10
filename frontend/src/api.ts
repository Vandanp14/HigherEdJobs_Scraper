// FastAPI errors arrive as {"detail": "..."}; show the detail text, not the raw JSON body.
const errorText = (body: string) => {
  try {
    const detail = JSON.parse(body)?.detail;
    return typeof detail === 'string' ? detail : body;
  } catch {
    return body;
  }
};

export const request = async (path: string, init?: RequestInit) => {
  const response = await fetch('/api' + path, init);
  if (!response.ok) throw new Error(errorText(await response.text()));
  return response.json();
};
