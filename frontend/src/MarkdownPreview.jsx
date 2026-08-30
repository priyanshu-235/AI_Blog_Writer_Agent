import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

export default function MarkdownPreview({ markdown }) {
  return (
    <div className="article">
      <Markdown remarkPlugins={[remarkGfm]}>{markdown}</Markdown>
    </div>
  );
}
