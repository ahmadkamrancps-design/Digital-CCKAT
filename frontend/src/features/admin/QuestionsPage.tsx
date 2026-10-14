import { useState } from "react";
import { allAdminRows, useAdminApi } from "../../services/admin";
import type {
  AdminGrading,
  AdminQuestion,
  AdminQuestionWrite,
  AdminSubject,
} from "../../types/admin";
import { Pager, RemoteStatus, TaskStatus, useRemote, useTask } from "./shared";

export function QuestionsPage() {
  const client = useAdminApi();
  const task = useTask();
  const [subject, setSubject] = useState("");
  const [type, setType] = useState("");
  const [active, setActive] = useState("");
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const [editing, setEditing] = useState<AdminQuestion | "new" | null>(null);
  const subjects = useRemote("bank-subjects", () =>
    allAdminRows<AdminSubject>(client, "/subjects"),
  );
  const list = useRemote(
    `${subject}:${type}:${active}:${search}:${offset}`,
    () =>
      client.list<AdminQuestion>("/questions", {
        ...(subject ? { subject_id: subject } : {}),
        ...(type ? { question_type: type } : {}),
        ...(active ? { is_active: active } : {}),
        search,
        limit: "50",
        offset: String(offset),
      }),
  );
  return (
    <>
      <h1>Question bank</h1>
      <p className="admin-muted">
        MCQs and short answers only. Keys and grading rules are available to
        administrators. Remove a question from every editable paper before
        changing it.
      </p>
      <button
        className="primary-button"
        disabled={editing !== null}
        onClick={() => setEditing("new")}
      >
        Create question
      </button>
      <TaskStatus task={task} />
      <RemoteStatus resource={subjects} />
      {editing && subjects.data && (
        <QuestionEditor
          key={editing === "new" ? "new" : editing.id}
          question={editing === "new" ? null : editing}
          subjects={subjects.data}
          saved={list.reload}
          close={() => setEditing(null)}
        />
      )}
      <section className="admin-panel">
        <div className="admin-toolbar">
          <label>
            Search prompts{" "}
            <input
              value={search}
              onChange={(event) => {
                setSearch(event.target.value);
                setOffset(0);
              }}
            />
          </label>
          <label>
            Filter subject{" "}
            <select
              value={subject}
              onChange={(event) => {
                setSubject(event.target.value);
                setOffset(0);
              }}
            >
              <option value="">All subjects</option>
              {subjects.data?.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Question type{" "}
            <select
              value={type}
              onChange={(event) => {
                setType(event.target.value);
                setOffset(0);
              }}
            >
              <option value="">All types</option>
              <option>MCQ</option>
              <option>SHORT_ANSWER</option>
            </select>
          </label>
          <label>
            Question status{" "}
            <select
              value={active}
              onChange={(event) => {
                setActive(event.target.value);
                setOffset(0);
              }}
            >
              <option value="">All statuses</option>
              <option value="true">Active</option>
              <option value="false">Archived</option>
            </select>
          </label>
        </div>
        <RemoteStatus resource={list} />
        <ul className="admin-bank-list">
          {list.data?.map((item) => (
            <li key={item.id}>
              <div className="admin-row">
                <span className="admin-badge">{item.type}</span>
                <span>
                  {
                    subjects.data?.find(
                      (subject) => subject.id === item.subject_id,
                    )?.name
                  }{" "}
                  · {item.marks} marks ·{" "}
                  {item.is_active ? "Active" : "Archived"}
                </span>
              </div>
              <p dir={item.direction} lang={item.language || undefined}>
                {item.prompt}
              </p>
              {item.type === "MCQ" ? (
                <ol type="A">
                  {item.options.map((option) => (
                    <li key={option.id} dir="auto">
                      {option.text}
                      {option.is_correct ? " · Correct answer" : ""}
                    </li>
                  ))}
                </ol>
              ) : (
                <p className="admin-muted">
                  Grading: {item.grading?.mode} · Accepted answers:{" "}
                  {item.accepted_answers.join(" | ") || "Manual review"}
                </p>
              )}
              <div className="admin-actions">
                <button
                  disabled={task.pending || editing !== null}
                  onClick={() => setEditing(item)}
                >
                  Edit question: {item.prompt.slice(0, 45)}
                </button>
                <button
                  disabled={task.pending || editing !== null || !item.is_active}
                  onClick={() => {
                    if (
                      !window.confirm(
                        "Archive this question? Questions still assigned to a paper cannot be archived.",
                      )
                    )
                      return;
                    void task.run(async () => {
                      await client.archiveQuestion(item.id);
                      await list.reload();
                    });
                  }}
                >
                  Archive question: {item.prompt.slice(0, 45)}
                </button>
              </div>
            </li>
          ))}
        </ul>
        {!list.loading && !list.error && !list.data?.length && (
          <p>No questions match these filters.</p>
        )}
        <Pager
          offset={offset}
          count={list.data?.length || 0}
          setOffset={setOffset}
        />
      </section>
    </>
  );
}
function QuestionEditor({
  question,
  subjects,
  saved,
  close,
}: {
  question: AdminQuestion | null;
  subjects: AdminSubject[];
  saved: () => Promise<void>;
  close: () => void;
}) {
  const client = useAdminApi();
  const task = useTask();
  const [subject, setSubject] = useState(question?.subject_id || "");
  const [type, setType] = useState<"MCQ" | "SHORT_ANSWER">(
    question?.type || "MCQ",
  );
  const [prompt, setPrompt] = useState(question?.prompt || "");
  const [marks, setMarks] = useState(question?.marks || "1.00");
  const [direction, setDirection] = useState<"auto" | "ltr" | "rtl">(
    question?.direction || "auto",
  );
  const [language, setLanguage] = useState(question?.language || "");
  const [active, setActive] = useState(question?.is_active ?? true);
  const [options, setOptions] = useState(
    question?.options.length
      ? question.options.map((option) => option.text)
      : ["", "", "", ""],
  );
  const [correct, setCorrect] = useState(
    question?.options.findIndex((option) => option.is_correct) ?? 0,
  );
  const [mode, setMode] = useState<AdminGrading["mode"]>(
    question?.grading?.mode || "EXACT",
  );
  const exact = question?.grading?.mode === "EXACT" ? question.grading : null;
  const [normalization, setNormalization] = useState<"NFC" | "NONE">(
    exact?.unicode_normalization || "NFC",
  );
  const [trim, setTrim] = useState(exact?.trim_whitespace ?? false);
  const [collapse, setCollapse] = useState(exact?.collapse_whitespace ?? false);
  const [caseSensitive, setCaseSensitive] = useState(
    exact?.case_sensitive ?? true,
  );
  const [tolerance, setTolerance] = useState(
    question?.grading?.mode === "NUMERIC"
      ? question.grading.absolute_tolerance
      : "0",
  );
  const [answers, setAnswers] = useState(
    question?.accepted_answers.join("\n") || "",
  );
  return (
    <section className="admin-panel">
      <h2>{question ? "Edit question" : "Create question"}</h2>
      <TaskStatus task={task} />
      <form
        className="admin-form"
        onSubmit={(event) => {
          event.preventDefault();
          void task.run(async () => {
            const base = {
              subject_id: subject,
              prompt,
              marks,
              direction,
              language: language || null,
              is_active: active,
            };
            const grading: AdminGrading =
              mode === "NUMERIC"
                ? { mode, absolute_tolerance: tolerance }
                : mode === "MANUAL"
                  ? { mode }
                  : {
                      mode,
                      unicode_normalization: normalization,
                      trim_whitespace: trim,
                      collapse_whitespace: collapse,
                      case_sensitive: caseSensitive,
                    };
            const value: AdminQuestionWrite =
              type === "MCQ"
                ? {
                    ...base,
                    type,
                    options: options.map((text, index) => ({
                      text,
                      is_correct: index === correct,
                    })),
                  }
                : {
                    ...base,
                    type,
                    grading,
                    accepted_answers:
                      mode === "MANUAL"
                        ? []
                        : answers.split("\n").filter((item) => item.trim()),
                  };
            await client.question(value, question?.id);
            await saved();
            close();
          });
        }}
      >
        <fieldset disabled={task.pending}>
          <legend>Question details</legend>
          <label>
            Question subject
            <select
              required
              value={subject}
              onChange={(event) => setSubject(event.target.value)}
            >
              <option value="">Choose subject</option>
              {subjects
                .filter(
                  (item) => item.is_active || item.id === question?.subject_id,
                )
                .map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
            </select>
          </label>
          <label>
            Type
            <select
              value={type}
              onChange={(event) => setType(event.target.value as typeof type)}
            >
              <option>MCQ</option>
              <option>SHORT_ANSWER</option>
            </select>
          </label>
          <label>
            Question prompt
            <textarea
              required
              maxLength={10000}
              value={prompt}
              dir={direction}
              lang={language || undefined}
              onChange={(event) => setPrompt(event.target.value)}
            />
          </label>
          <div className="admin-row">
            <label>
              Marks
              <input
                type="number"
                min="0.01"
                max="10000"
                step="0.01"
                required
                value={marks}
                onChange={(event) => setMarks(event.target.value)}
              />
            </label>
            <label>
              Text direction
              <select
                value={direction}
                onChange={(event) =>
                  setDirection(event.target.value as typeof direction)
                }
              >
                <option value="auto">Automatic</option>
                <option value="ltr">Left to right</option>
                <option value="rtl">Right to left</option>
              </select>
            </label>
            <label>
              Language code (optional)
              <input
                value={language}
                maxLength={35}
                placeholder="en / ur"
                onChange={(event) => setLanguage(event.target.value)}
              />
            </label>
          </div>
          <label className="admin-check">
            <input
              type="checkbox"
              checked={active}
              onChange={(event) => setActive(event.target.checked)}
            />
            Active question
          </label>
          {type === "MCQ" ? (
            <fieldset>
              <legend>Options — select exactly one correct answer</legend>
              <div className="admin-options">
                {options.map((text, index) => (
                  <div key={index} className="admin-row">
                    <label className="admin-check">
                      <input
                        type="radio"
                        name="correct-option"
                        required
                        checked={correct === index}
                        onChange={() => setCorrect(index)}
                      />
                      Correct {String.fromCharCode(65 + index)}
                    </label>
                    <input
                      aria-label={`Option ${String.fromCharCode(65 + index)} text`}
                      type="text"
                      required
                      maxLength={4000}
                      dir="auto"
                      value={text}
                      onChange={(event) =>
                        setOptions((previous) =>
                          previous.map((value, position) =>
                            position === index ? event.target.value : value,
                          ),
                        )
                      }
                    />
                    <button
                      type="button"
                      disabled={options.length <= 2}
                      aria-label={`Remove option ${String.fromCharCode(65 + index)}`}
                      onClick={() => {
                        setOptions((previous) =>
                          previous.filter((_, position) => position !== index),
                        );
                        setCorrect((previous) =>
                          previous === index
                            ? 0
                            : previous > index
                              ? previous - 1
                              : previous,
                        );
                      }}
                    >
                      Remove
                    </button>
                  </div>
                ))}
              </div>
              <button
                type="button"
                disabled={options.length >= 8}
                onClick={() => setOptions((previous) => [...previous, ""])}
              >
                Add option
              </button>
            </fieldset>
          ) : (
            <fieldset>
              <legend>Short-answer grading configuration</legend>
              <label>
                Grading mode
                <select
                  value={mode}
                  onChange={(event) =>
                    setMode(event.target.value as typeof mode)
                  }
                >
                  <option>EXACT</option>
                  <option>NUMERIC</option>
                  <option>MANUAL</option>
                </select>
              </label>
              {mode === "EXACT" && (
                <>
                  <label>
                    Unicode normalization
                    <select
                      value={normalization}
                      onChange={(event) =>
                        setNormalization(
                          event.target.value as typeof normalization,
                        )
                      }
                    >
                      <option>NFC</option>
                      <option>NONE</option>
                    </select>
                  </label>
                  <label className="admin-check">
                    <input
                      type="checkbox"
                      checked={trim}
                      onChange={(event) => setTrim(event.target.checked)}
                    />
                    Trim surrounding whitespace
                  </label>
                  <label className="admin-check">
                    <input
                      type="checkbox"
                      checked={collapse}
                      onChange={(event) => setCollapse(event.target.checked)}
                    />
                    Collapse whitespace
                  </label>
                  <label className="admin-check">
                    <input
                      type="checkbox"
                      checked={caseSensitive}
                      onChange={(event) =>
                        setCaseSensitive(event.target.checked)
                      }
                    />
                    Case sensitive
                  </label>
                </>
              )}
              {mode === "NUMERIC" && (
                <label>
                  Absolute tolerance
                  <input
                    type="number"
                    required
                    min="0"
                    max="1000000"
                    step="any"
                    value={tolerance}
                    onChange={(event) => setTolerance(event.target.value)}
                  />
                </label>
              )}
              {mode !== "MANUAL" ? (
                <label>
                  Accepted answers (one per line)
                  <textarea
                    required
                    value={answers}
                    dir="auto"
                    onChange={(event) => setAnswers(event.target.value)}
                  />
                </label>
              ) : (
                <p>
                  Responses will need an authorized examiner in the grading
                  milestone.
                </p>
              )}
            </fieldset>
          )}
          <div className="admin-actions">
            <button className="primary-button">Save question</button>
            <button type="button" onClick={close}>
              Cancel question editing
            </button>
          </div>
        </fieldset>
      </form>
      <h3>Prompt preview</h3>
      <p
        dir={direction}
        lang={language || undefined}
        style={{ whiteSpace: "pre-wrap" }}
      >
        {prompt || "Enter a question prompt above."}
      </p>
    </section>
  );
}
