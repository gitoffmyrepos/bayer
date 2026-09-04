export function MarkdownText({ content }: { content: string }) {
  const blocks = content.split(/\n\s*\n/).filter(Boolean);
  return (
    <div className="learning-copy">
      {blocks.map((block, index) => {
        const heading = block.match(/^#{1,6}\s+(.+)/);
        if (heading) return <h3 key={index}>{heading[1]}</h3>;
        if (/^[-*]\s+/m.test(block)) {
          return (
            <ul key={index}>
              {block.split("\n").map((line) => <li key={line}>{line.replace(/^[-*]\s+/, "")}</li>)}
            </ul>
          );
        }
        return <p key={index}>{block.replace(/\*\*/g, "")}</p>;
      })}
    </div>
  );
}
