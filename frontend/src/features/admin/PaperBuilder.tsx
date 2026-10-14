import { useState } from "react";
import { allAdminRows, useAdminApi } from "../../services/admin";
import type {
  AdminPaper,
  AdminPaperEntry,
  AdminQuestion,
} from "../../types/admin";
import { RemoteStatus, TaskStatus, useRemote, useTask } from "./shared";

export function PaperBuilder({
  paperId,
  subjectId,
  frozen,
  saved,
}: {
  paperId: string;
  subjectId: string;
  frozen: boolean;
  saved: () => Promise<void>;
}) {
  const client = useAdminApi();
  const resource = useRemote(paperId, async () => {
    const [paper, questions] = await Promise.all([
      client.paper(paperId),
      allAdminRows<AdminQuestion>(client, "/questions", {
        subject_id: subjectId,
      }),
    ]);
    return { paper, questions };
  });
  return (
    <section className="admin-panel">
      <h2>Exam paper builder</h2>
      <RemoteStatus resource={resource} />
      {resource.data && (
        <PaperEditor
          key={`${paperId}:${resource.data.paper.questions.map((item) => item.id).join(",")}`}
          paper={resource.data.paper}
          questions={resource.data.questions}
          frozen={frozen}
          saved={async () => {
            await resource.reload();
            await saved();
          }}
        />
      )}
    </section>
  );
}
function PaperEditor({
  paper,
  questions,
  frozen,
  saved,
}: {
  paper: AdminPaper;
  questions: AdminQuestion[];
  frozen: boolean;
  saved: () => Promise<void>;
}) {
  const client = useAdminApi();
  const task = useTask();
  const [search, setSearch] = useState("");
  const [entries, setEntries] = useState<AdminPaperEntry[]>(
    paper.questions.map(({ question_id, marks_override }) => ({
      question_id,
      marks_override,
    })),
  );
  const move = (index: number, delta: number) =>
    setEntries((previous) => {
      const next = [...previous];
      [next[index], next[index + delta]] = [next[index + delta], next[index]];
      return next;
    });
  return (
    <>
      <p>
        Saved paper: {paper.questions.length} questions · {paper.total_marks}{" "}
        marks. Draft selection: {entries.length} questions.
      </p>
      <TaskStatus task={task} />
      {frozen && (
        <p className="admin-alert">
          Paper editing is locked. You can inspect the existing selection.
        </p>
      )}
      <form
        onSubmit={(event) => {
          event.preventDefault();
          if (
            !window.confirm(
              `Save this ordered paper with ${entries.length} questions?`,
            )
          )
            return;
          void task.run(async () => {
            await client.savePaper(paper.exam_subject_id, entries);
            await saved();
          }, "Paper selection saved.");
        }}
      >
        <fieldset disabled={frozen || task.pending}>
          <legend>Selected questions (maximum 200)</legend>
          <ol className="admin-paper-list">
            {entries.map((entry, index) => {
              const question = questions.find(
                (item) => item.id === entry.question_id,
              );
              return (
                <li key={entry.question_id}>
                  <p
                    dir={question?.direction || "auto"}
                    lang={question?.language || undefined}
                  >
                    {question?.prompt || entry.question_id}
                  </p>
                  <div className="admin-row">
                    <label>
                      Marks override for question {index + 1}{" "}
                      <input
                        type="number"
                        min="0.01"
                        max="10000"
                        step="0.01"
                        placeholder={question?.marks}
                        value={entry.marks_override || ""}
                        onChange={(event) =>
                          setEntries((previous) =>
                            previous.map((item) =>
                              item.question_id === entry.question_id
                                ? {
                                    ...item,
                                    marks_override: event.target.value || null,
                                  }
                                : item,
                            ),
                          )
                        }
                      />
                    </label>
                    <button
                      type="button"
                      aria-label={`Move question ${index + 1} earlier`}
                      disabled={index === 0}
                      onClick={() => move(index, -1)}
                    >
                      ↑
                    </button>
                    <button
                      type="button"
                      aria-label={`Move question ${index + 1} later`}
                      disabled={index === entries.length - 1}
                      onClick={() => move(index, 1)}
                    >
                      ↓
                    </button>
                    <button
                      type="button"
                      onClick={() =>
                        setEntries((previous) =>
                          previous.filter(
                            (item) => item.question_id !== entry.question_id,
                          ),
                        )
                      }
                    >
                      Remove question {index + 1}
                    </button>
                  </div>
                </li>
              );
            })}
          </ol>
          <button className="primary-button">Save ordered paper</button>
        </fieldset>
      </form>
      <h3>Available question bank</h3>
      <label>
        Find available questions{" "}
        <input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
      </label>
      <ul className="admin-bank-list">
        {questions
          .filter(
            (question) =>
              question.is_active &&
              !entries.some((entry) => entry.question_id === question.id) &&
              question.prompt
                .toLocaleLowerCase()
                .includes(search.toLocaleLowerCase()),
          )
          .map((question) => (
            <li key={question.id}>
              <p dir={question.direction} lang={question.language || undefined}>
                {question.prompt}
              </p>
              <div className="admin-row">
                <span>
                  {question.type} · {question.marks} marks
                </span>
                <button
                  disabled={frozen || task.pending || entries.length >= 200}
                  onClick={() =>
                    setEntries((previous) => [
                      ...previous,
                      { question_id: question.id, marks_override: null },
                    ])
                  }
                >
                  Add question: {question.prompt.slice(0, 60)}
                </button>
              </div>
            </li>
          ))}
      </ul>
    </>
  );
}
