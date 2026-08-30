export function apiBaseUrl() {
  const configured = import.meta.env.VITE_API_URL?.trim();

  if (configured) {
    return configured.replace(/\/$/, "");
  }

  return "";
}

export function blogToState(blog) {
  return {
    topic: blog.topic,
    routing_strategy: blog.routing_strategy,
    research_needed: blog.research_needed,
    search_queries: blog.search_queries ?? [],
    collected_sources: blog.sources ?? [],
    blog_outline: blog.outline ?? null,
    diagram_assets: (blog.diagrams ?? []).map((diagram) => ({
      filename: diagram.filename,
      url: diagram.secure_url,
      alt_text: diagram.alt_text,
      caption: diagram.caption,
      cloudinary_public_id: diagram.cloudinary_public_id,
      resource_type: diagram.resource_type,
    })),
    final_markdown: blog.markdown,
  };
}

export async function generateBlog(topic, currentDate, onEvent, signal) {
  const response = await fetch(`${apiBaseUrl()}/api/generate`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      topic,
      current_date: currentDate,
    }),
    signal,
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed (${response.status})`);
  }

  if (!response.body) {
    throw new Error("The API did not return a stream.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();

    if (done) {
      break;
    }

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      const trimmed = line.trim();

      if (!trimmed) {
        continue;
      }

      onEvent(JSON.parse(trimmed));
    }
  }

  if (buffer.trim()) {
    onEvent(JSON.parse(buffer.trim()));
  }
}

export async function listBlogs() {
  const response = await fetch(`${apiBaseUrl()}/api/blogs`);

  if (!response.ok) {
    throw new Error("Could not load saved blogs.");
  }

  const payload = await response.json();
  return payload.blogs ?? [];
}

export async function getBlog(id) {
  const response = await fetch(`${apiBaseUrl()}/api/blogs/${id}`);

  if (!response.ok) {
    throw new Error("Blog not found.");
  }

  return response.json();
}

export async function deleteBlog(id) {
  const response = await fetch(`${apiBaseUrl()}/api/blogs/${id}`, {
    method: "DELETE",
  });

  if (!response.ok) {
    throw new Error("Could not delete blog.");
  }
}
