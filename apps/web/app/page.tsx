import { Quiz } from "@/components/Quiz";
import { loadBundle } from "@/lib/bundle";

export default async function HomePage() {
  const { manifest, questions } = await loadBundle();

  return (
    <main className="page">
      <header className="site-header">
        <h1>CCNA Learning Platform</h1>
        <p className="subtitle">
          {manifest.source.filename} · {manifest.question_count} questions
        </p>
      </header>
      {questions.length > 0 ? (
        <Quiz questions={questions} />
      ) : (
        <p className="empty">
          No questions loaded. Generate a bundle with{" "}
          <code>qbank-import json content/sample-networking.json --out apps/web/content/bundle</code>
          .
        </p>
      )}
    </main>
  );
}
