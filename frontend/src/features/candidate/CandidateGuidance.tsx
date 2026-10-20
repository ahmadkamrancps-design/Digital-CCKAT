import { Link } from 'react-router-dom';

export function ExamInstructions() {
  return <>
    <div className="candidate-notice">
      <strong>Start only when your proctor gives permission.</strong>
      <p>Check My Exam for your assigned subjects, their order, time limits, and schedule. Follow the instructions for your assigned paper and any directions given by the examination staff.</p>
    </div>
    <div className="candidate-guidance-grid">
      <section aria-labelledby="before-exam-heading">
        <h2 id="before-exam-heading">1. Before you begin</h2>
        <ul>
          <li>Check your name and admissions roll number in <Link to="/profile">your candidate profile</Link>. Report any incorrect details before starting.</li>
          <li>Complete the <Link to="/system-check">device and connection checks</Link>. Connect your laptop to power and keep one exam tab open.</li>
          <li>Have your roll number slip and any identification requested by CCK ready for verification.</li>
          <li>Use only materials and tools permitted by the examination staff. Ask your proctor about calculators, rough paper, breaks, or other arrangements before you begin.</li>
        </ul>
      </section>
      <section aria-labelledby="subject-time-heading">
        <h2 id="subject-time-heading">2. Subjects and time limits</h2>
        <ul>
          <li>Each subject has its own timer. Selecting Start subject starts that subject’s allotted time.</li>
          <li>The server controls the deadline. Refreshing, signing in again, changing your device clock, or losing your connection does not give extra time.</li>
          <li>Check the exam’s scheduled closing time as well as the subject timer. The exam closing time can end a subject before its full allowance is used.</li>
          <li>Work within the current subject. Complete it before moving to the next subject in the assigned order.</li>
          <li>When time ends, editing stops and the subject closes automatically. Answers received and accepted by the server before the deadline are preserved.</li>
        </ul>
      </section>
      <section aria-labelledby="answering-heading">
        <h2 id="answering-heading">3. Answering questions</h2>
        <ul>
          <li>For an MCQ, select one option. Select a different option to change your answer, or choose Clear Answer to remove it.</li>
          <li>Crossing out an option is a reading aid; it does not select or clear your answer. Check which option is selected.</li>
          <li>For a short answer, type only the response requested. Read any instructions about units, numbers, spelling, or language carefully.</li>
          <li>For Urdu responses, use your Urdu keyboard. You can practise typing on the System Check page before starting.</li>
        </ul>
      </section>
      <section aria-labelledby="review-heading">
        <h2 id="review-heading">4. Navigation and review</h2>
        <ul>
          <li>Use Previous, Next, or a numbered question in the overview to move within the current subject.</li>
          <li>The overview shows answered and unanswered questions. Mark for Review helps you find a question again; it does not answer the question for you.</li>
          <li>You can change answers and remove review marks while the subject is active.</li>
          <li>Before finishing, check unanswered questions and revisit anything you marked for review.</li>
        </ul>
      </section>
      <section aria-labelledby="saving-heading">
        <h2 id="saving-heading">5. Saving and connection problems</h2>
        <dl className="candidate-save-guide">
          <div><dt>Saving…</dt><dd>Your latest change is being sent to the server.</dd></div>
          <div><dt>Saved</dt><dd>Your current answer has been acknowledged by the server.</dd></div>
          <div><dt>Offline / waiting to sync</dt><dd>Changes are waiting to synchronize. Keep the exam window open and alert your proctor.</dd></div>
          <div><dt>Sync problem</dt><dd>Read the message on screen and ask your proctor for assistance.</dd></div>
        </dl>
        <p>A local recovery copy is not server confirmation. Reconnection cannot extend the deadline. Do not clear browser data, sign out, or change devices while answers are waiting to sync.</p>
      </section>
      <section aria-labelledby="finishing-heading">
        <h2 id="finishing-heading">6. Submission and results</h2>
        <ul>
          <li>When ready, choose Finish, read the confirmation, and select Submit subject. Wait for the submission confirmation.</li>
          <li>A submitted or expired subject is locked. You cannot return to change its answers.</li>
          <li>Follow the next-subject prompt and your proctor’s directions. Stay at your workstation until examination staff allow you to leave.</li>
          <li>After the last subject, check the final submission confirmation. Results appear only when administration releases them.</li>
        </ul>
      </section>
    </div>
    <section className="candidate-notice" aria-labelledby="conduct-heading">
      <h2 id="conduct-heading">Examination conduct</h2>
      <p>Work independently. Do not share questions, photograph the paper, use messaging or unauthorized websites, or receive help with answers. Tell your proctor promptly about a technical problem or a need for assistance. Examination staff decide how to handle incidents.</p>
    </section>
    <div className="candidate-page-actions">
      <Link className="secondary-button" to="/system-check">Check my device</Link>
      <Link className="primary-button" to="/exam">My Exam →</Link>
    </div>
  </>;
}

export function SystemCheckGuidance() {
  return <section className="candidate-guidance-section" aria-labelledby="manual-checks-heading">
    <h2 id="manual-checks-heading">Prepare your workstation</h2>
    <ul>
      <li>Connect to power and use the test-centre network specified by your proctor.</li>
      <li>Close extra exam tabs and unrelated applications before starting. Avoid private browsing and allow this site to use browser storage.</li>
      <li>Check that text, question options, and navigation are clearly visible. Use your browser’s zoom controls if needed.</li>
      <li>Try the keyboard below. Check Urdu input before starting if your assigned paper requires it.</li>
      <li>If any automatic check needs attention, ask your proctor for help before starting your subject.</li>
    </ul>
    <label className="candidate-typing-label" htmlFor="readiness-typing">Keyboard practice — not an exam answer</label>
    <input id="readiness-typing" className="candidate-typing-input" type="text" dir="auto" maxLength={200} autoComplete="off" spellCheck={false} placeholder="Try English, 123, or اردو" aria-describedby="typing-explanation" />
    <p id="typing-explanation">This practice text is not saved or submitted. Use Tab and Shift+Tab to check keyboard navigation and the visible focus outline.</p>
    <p lang="ur" dir="rtl">اردو لکھنے کے لیے اپنا اردو کی بورڈ منتخب کریں اور یہاں لکھ کر دیکھیں۔</p>
    <p>If a problem occurs after your test has started, keep the exam window open and call your proctor before changing browser settings.</p>
    <div className="candidate-page-actions"><Link className="secondary-button" to="/instructions">Read exam instructions</Link><Link className="primary-button" to="/exam">Go to My Exam →</Link></div>
  </section>;
}

export function HelpAndSupport() {
  return <>
    <section className="candidate-notice" aria-labelledby="during-test-heading">
      <h2 id="during-test-heading">Need help during a timed subject?</h2>
      <p>Raise your hand or use the assistance method announced by your test centre. Keep the exam window open and tell your proctor what happened. The timer continues during a connection problem.</p>
      <p>Do not sign out, clear browser storage, switch devices, or repeatedly refresh while work is waiting to sync.</p>
    </section>
    <section className="candidate-guidance-section" aria-labelledby="common-questions-heading">
      <h2 id="common-questions-heading">Common questions</h2>
      <div className="candidate-faq">
        <details><summary>I cannot sign in with my admissions details</summary><p>Use the roll number assigned through CCK admissions, your full name, and your father’s name as recorded in your approved registration. Do not create a second registration or keep guessing. Ask admissions to check the record if the details are rejected.</p></details>
        <details><summary>My exam is missing or waiting for authorization</summary><p>Check that you are using your own approved candidate account. Administration must assign and authorize the exam before you can start. Ask your proctor or admissions to verify the assignment and schedule.</p></details>
        <details><summary>My answer says Offline or Sync problem</summary><p>Keep the current exam window open and alert your proctor. The application attempts safe synchronization after reconnection. Watch for Saved; work stored only on your device may not be accepted after the server deadline.</p></details>
        <details><summary>The browser closed or my device stopped working</summary><p>Tell your proctor immediately. Reopen the official test address on the same device and browser profile when instructed, sign in if required, and resume the existing attempt through My Exam. Changing devices cannot transfer unsynchronized local work or restart a timer.</p></details>
        <details><summary>I see a conflict between a recovered and a saved answer</summary><p>Read the recovery message carefully. Compare the current server answer with the recovered draft before choosing which to keep. Ask your proctor if you are unsure; do not clear storage to remove the message.</p></details>
        <details><summary>Can I reopen a submitted subject or get more time?</summary><p>Submitted and expired subjects cannot be edited. Refreshing or signing in again does not restart time. Report any exceptional circumstances to examination staff for review; the candidate portal cannot grant an extension.</p></details>
        <details><summary>Why can I not see my result?</summary><p>Submission does not immediately publish a result. Some responses may require examiner review. Administration controls when results are released; check the Results page when CCK announces availability.</p></details>
      </div>
    </section>
    <section className="candidate-guidance-section" aria-labelledby="report-problem-heading">
      <h2 id="report-problem-heading">What to tell your proctor or admissions</h2>
      <p>Give your roll number, the exam and subject, the question number if relevant, the approximate time, and the exact error message or save status. Describe what happened without sharing a question, answer, or screenshot of exam content.</p>
      <p>Do not send your father’s name, sign-in details, or browser session information in a support email.</p>
    </section>
    <section className="candidate-guidance-section" aria-labelledby="contact-admissions-heading">
      <h2 id="contact-admissions-heading">Registration and admissions enquiries</h2>
      <p>Before your test, contact CCK admissions for registration corrections or roll-number enquiries. During a timed test, contact your on-site proctor first.</p>
      <dl className="candidate-profile-details">
        <div><dt>Admissions email</dt><dd><a href="mailto:admissions@cck.edu.pk">admissions@cck.edu.pk</a></dd></div>
        <div><dt>College telephone</dt><dd><a href="tel:+92922864600">+92 922 864600</a> / <a href="tel:+92922864601">864601</a></dd></div>
      </dl>
      <p className="candidate-source">Published contacts: <a href="https://www.cck.edu.pk/academic/admissions_process/" target="_blank" rel="noreferrer">CCK admissions guidance (new tab)</a> and <a href="https://www.cck.edu.pk/" target="_blank" rel="noreferrer">CCK website (new tab)</a>. These are college contact channels; no live support ticket is created by this page.</p>
    </section>
  </>;
}
