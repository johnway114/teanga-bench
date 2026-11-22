"""Blas Open Lab pages, rendered into the Blas suite's static site."""

import json
from dataclasses import dataclass
from html import escape
from pathlib import Path
from urllib.parse import urlsplit


BLAS = "https://blasapp.com"
BLASBENCH = "https://github.com/jyoutir/blasbench"
BLASBENCH_RELEASE = "560e0220da07bff0d884ab519b2dbc11c8462b30"
MODEL_CARD = "https://huggingface.co/jyoutir/blas-m3-lm"
LAB_TITLE = "Blas Open Lab"


@dataclass(frozen=True)
class _Page:
    slug: str
    label: str
    title: str
    description: str
    body: str
    script: str = ""


@dataclass(frozen=True)
class _Clip:
    voice: str
    audio_url: str
    rights_url: str


@dataclass(frozen=True)
class _ListeningPair:
    text: str
    text_source: str
    clips: tuple[_Clip, _Clip]


def _approved_url(value: str) -> str:
    url = urlsplit(value)
    if url.scheme != "https" or not url.hostname or url.username or url.password:
        raise ValueError("Lab evidence must use public HTTPS URLs")
    return value


def _listening_pair(manifest: Path | None) -> _ListeningPair | None:
    """Accept only an explicitly reviewed public playback manifest, never cache assets."""
    if manifest is None or not manifest.is_file():
        return None
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
        text = data["text"].strip()
        if data["language"] != "ga" or data["public_playback_approved"] is not True or not text:
            return None
        clips = tuple(
            _Clip(clip["voice"].strip(), _approved_url(clip["audio_url"]), _approved_url(clip["rights_url"]))
            for clip in data["clips"]
        )
        if len(clips) != 2:
            return None
        left, right = clips
        if not left.voice or not right.voice or left.voice == right.voice or left.audio_url == right.audio_url:
            return None
        return _ListeningPair(text, _approved_url(data["text_source_url"]), (left, right))
    except (OSError, TypeError, ValueError, KeyError, AttributeError):
        return None


def _card(title: str, note: str, href: str, action: str) -> str:
    return (
        f'<article class="card"><h2>{escape(title)}</h2><p>{escape(note)}</p>'
        f'<p class="card-foot"><a href="{escape(href)}">{escape(action)}</a></p></article>'
    )


def _overview() -> str:
    return (
        '<div class="cards lab-cards">'
        + _card("Speech studio", "See which Celtic voices have public playback or synthesis clearance.", "speech.html", "Explore speech")
        + _card("Dictation & subtitles", "Record Irish or open a local media file. Edit and export subtitle cues in your browser.", "transcribe.html", "Open the workspace")
        + _card("Writing & proofing", "Check Irish and Welsh writing with Blas’s grammar and mutation tools.", "write.html", "Find a proofing tool")
        + _card("Benchmarks", "Compare published language-model and Irish speech-recognition results at their sources.", "benchmarks.html", "Explore the evidence")
        + _card("Blind listening", "Read how we separate listener preferences from automatic speech scores.", "arena.html", "Read the listening protocol")
        + _card("Developers", "Get the public Irish ASR model, benchmark data and Blas API documentation.", "developers.html", "Browse developer resources")
        + "</div>"
    )


def _speech(pair: _ListeningPair | None) -> str:
    if pair:
        return (
            f'<p class="lab-studio-text" lang="ga">{escape(pair.text)}</p>'
            '<div class="cards lab-cards">'
            + "".join(
                f'<section class="card"><h2>{escape(clip.voice)}</h2>'
                f'<audio controls preload="none" aria-label="{escape(clip.voice)}" src="{escape(clip.audio_url)}"></audio>'
                f'<p class="card-foot"><a href="{escape(clip.rights_url)}">Playback rights and attribution</a></p></section>'
                for clip in pair.clips
            )
            + '</div><p>No arbitrary-text synthesis or downloadable voice weights are provided in the studio.</p>'
            f'<p><a href="{escape(pair.text_source)}">Sentence source</a></p>'
            '<p class="lab-note"><a href="arena.html">Hear the comparison blind</a></p>'
        )
    return f"""
<div class="lab-notice notice"><strong>No clips or synthesis are cleared for this studio.</strong>
<p>Public playback, arbitrary synthesis and open-weight distribution require separate checks. Private Irish voices are not playable or downloadable here.</p></div>
<div class="lab-disclosures">
  <details class="drill" open><summary><strong>Irish</strong></summary><div class="drill-body">
    <p>Connacht, Munster and Ulster listening comparisons are unavailable. The proposed pronunciation inspector and browser synthesis are not public releases.</p>
    <p><a href="{BLAS}/dictionary?language=irish">Browse attested Irish dictionary entries</a></p>
  </div></details>
  <details class="drill"><summary><strong>Welsh</strong></summary><div class="drill-body">
    <p>The North and South Welsh voices have no cleared public synthesis demo here.</p>
    <p><a href="{BLAS}/dictionary?language=welsh">Browse the Welsh dictionary</a></p>
  </div></details>
  <details class="drill"><summary><strong>Breton</strong></summary><div class="drill-body">
    <p>Breton synthesis is not available in this studio.</p>
    <p><a href="{BLAS}/dictionary?language=breton">Browse the Breton dictionary</a></p>
  </div></details>
</div>
<p class="lab-note">Looking for speech to text instead? <a href="transcribe.html">Open Irish dictation and subtitles</a>.</p>
"""


def _transcribe(turnstile_site_key: str) -> str:
    service_message = (
        "Automatic transcription sends short audio clips to the isolated Blas service."
        if turnstile_site_key else
        "Automatic transcription is unavailable. You can still preview media, edit cues and export locally."
    )
    return f"""
<div id="transcription" data-site-key="{escape(turnstile_site_key)}">
  <nav class="lab-mode" aria-label="Transcription tools">
    <a class="lab-button" href="#dictation">Microphone dictation</a>
    <a class="lab-button" href="#subtitler">File subtitler</a>
  </nav>
  <noscript><p class="notice">Dictation and the local subtitle editor require JavaScript.</p></noscript>
  <section class="card lab-service" aria-label="Audio processing consent" data-js hidden>
    <p id="asr-state" role="status">{service_message}</p>
    <label id="upload-consent" class="lab-check" hidden><input type="checkbox" id="consent">
      <span>I agree to send short audio clips to Blas for transcription. The original media file is never uploaded.</span>
    </label>
    <div id="verification" class="lab-verification"></div>
    <details class="lab-privacy"><summary>Audio and quota privacy</summary>
      <p>Blas does not keep audio or transcripts or use them for training. Cloudflare Turnstile receives your IP address and challenge token for verification.</p>
      <p>To enforce the daily limit, the isolated service stores a keyed hash of your IP, the UTC date and seconds used, plus a daily total. It does not store your raw IP. Old quota entries are removed when the service next accepts a request on a later UTC day, so they can remain longer if the service is idle.</p>
    </details>
  </section>
  <section id="dictation" class="card lab-workspace" aria-labelledby="dictation-heading" data-js hidden>
    <div class="lab-tool-head"><div><p class="eyebrow">Microphone · 30 seconds</p><h2 id="dictation-heading">Éist dictation</h2></div>
      <a href="{BLAS}/research/dictate">Blas Dictation for Mac</a>
    </div>
    <div class="lab-editor-grid">
      <div class="lab-well">
        <div class="lab-record-time"><span id="record-time">0:00</span> <span class="muted">/ 0:30</span></div>
        <meter id="record-level" min="0" max="1" value="0" aria-label="Microphone level"></meter>
        <div class="lab-actions"><button type="button" class="lab-primary" id="record">Record</button>
          <button type="button" id="clear-recording" disabled>Discard recording</button></div>
        <audio id="recording" controls hidden aria-label="Recorded audio"></audio>
        <div class="lab-actions"><button type="button" id="send-recording" disabled>Transcribe recording</button></div>
        <p class="lab-note" id="record-status" role="status">You can listen back before sending.</p>
      </div>
      <div>
        <label for="dictation-text">Transcript</label>
        <textarea lang="ga" id="dictation-text" rows="5" placeholder="Speak Irish or enter text to edit here."></textarea>
        <div class="lab-actions"><button type="button" id="copy-dictation" disabled>Copy transcript</button>
          <button type="button" id="download-dictation" disabled>Download TXT</button></div>
        <p id="dictation-status" class="lab-note" role="status"></p>
      </div>
    </div>
  </section>
  <section id="subtitler" class="card lab-workspace" aria-labelledby="subtitler-heading" data-js hidden>
    <div class="lab-tool-head"><div><p class="eyebrow">Audio or video · 2 minutes for extraction</p>
      <h2 id="subtitler-heading">Tras-scríobh subtitler</h2></div></div>
    <div class="lab-editor-grid">
      <div>
        <label class="lab-drop" id="drop-zone" for="media-file">
          <strong>Choose or drop a media file</strong><span>WAV, MP3, M4A, MP4 or MOV · up to 100 MiB</span>
          <input type="file" id="media-file" accept="audio/*,video/*,.mp3,.m4a,.wav,.mp4,.mov">
        </label>
        <p id="file-name" class="lab-note"></p>
        <div class="lab-actions"><button type="button" id="preview-file" disabled aria-controls="media-preview" aria-expanded="false">Preview media</button></div>
        <p id="preview-status" class="lab-note" role="status"></p>
        <div id="media-preview" class="lab-preview" hidden></div>
        <p id="playing-cue" class="lab-caption" lang="ga" hidden></p>
        <div class="lab-actions"><button type="button" class="lab-primary" id="send-file" disabled>Generate subtitle cues</button>
          <button type="button" id="extract-audio" disabled>Extract audio locally</button>
          <button type="button" id="clear-file" disabled>Close media</button>
          <button type="button" id="cancel-file" hidden>Cancel processing</button></div>
        <a id="save-audio" class="lab-button" hidden download="extracted-irish-audio.wav">Save extracted WAV</a>
        <p class="lab-note" id="file-status" role="status">Only the audio is extracted, in your browser. Codec support varies by browser.</p>
      </div>
      <div>
        <h3>Subtitle cues</h3>
        <p class="lab-note">Edit times (in seconds) and text. Open a cue’s dictionary tools to look up a word.</p>
        <ol id="cues" class="lab-cues"></ol>
        <div class="lab-actions"><button type="button" id="add-cue">Add cue</button></div>
        <div class="lab-actions lab-export" aria-label="Download subtitles">
          <button type="button" data-export="srt" disabled>Download SRT</button>
          <button type="button" data-export="vtt" disabled>Download VTT</button>
          <button type="button" data-export="txt" disabled>Download TXT</button>
        </div>
        <p class="lab-note" id="cue-status" role="status"></p>
      </div>
    </div>
  </section>
</div>
"""


def _proofing() -> str:
    return (
        '<div class="cards lab-cards">'
        + _card("Writing checker", "Run Blas’s existing checks and read the suggested changes.", f"{BLAS}/grammar-checker", "Open the writing checker")
        + _card("Irish mutations", "Check lenition and eclipsis in Irish.", f"{BLAS}/irish/mutation-checker", "Check Irish")
        + _card("Welsh mutations", "Check soft, nasal and aspirate mutations in Welsh.", f"{BLAS}/welsh/mutation-checker", "Check Welsh")
        + _card("Aural proofing", "Optionally read back with a matching voice installed on your device. Cleared Blas dialect synthesis is not available.", f"{BLAS}/grammar-checker", "Open device read-back")
        + "</div>"
    )


def _benchmarks() -> str:
    return f"""
<div class="cards lab-cards">
  <article class="card"><h2>Teanga Bench</h2><p>Language-model performance across six Celtic languages, with published scores and uncertainty.</p>
    <p class="card-foot"><a href="./">Explore the Teanga leaderboard</a></p>
    <p class="lab-note"><a href="methodology.html">Methodology</a> · <a href="data/leaderboard.json">Leaderboard JSON</a></p>
  </article>
  <article class="card"><h2>Dialect TTS ruler</h2><p>No cleared dialect or connected-speech evaluation artifact is available in this Lab. Error rates and phonetic contrasts would not replace fluent listening.</p>
    <p class="card-foot"><a href="arena.html">See the blind listening protocol</a></p>
  </article>
</div>
<section class="card lab-workspace" id="blasbench" data-revision="{BLASBENCH_RELEASE}" aria-labelledby="blasbench-heading">
  <div class="lab-tool-head"><div><p class="eyebrow">Irish speech recognition</p><h2 id="blasbench-heading">BlasBench v0.1.0</h2></div>
    <a href="{BLASBENCH}/tree/{BLASBENCH_RELEASE}">Source and methodology</a></div>
  <p>Compare published Common Voice and FLEURS runs on word error rate (WER) or character error rate (CER). Lower is better; insertions can push rates over 100%.</p>
  <div class="lab-actions"><button type="button" class="lab-primary" id="load-blasbench" hidden>Load published results</button>
    <a href="{BLASBENCH}/blob/{BLASBENCH_RELEASE}/results/summary.csv">Release CSV</a>
    <a href="{MODEL_CARD}">Blas-IE model card &amp; results</a></div>
  <p id="blasbench-status" class="lab-note" role="status"></p>
  <div id="blasbench-results" hidden>
    <div class="lab-actions lab-filters">
      <label for="blasbench-dataset">Dataset <select id="blasbench-dataset"><option value="cv-corpus-25.0-ga-IE">Common Voice 25.0 · ga-IE</option><option value="google/fleurs">FLEURS · ga-IE</option></select></label>
      <label for="blasbench-metric">Rank by <select id="blasbench-metric"><option value="wer">Word error rate</option><option value="cer">Character error rate</option></select></label>
    </div>
    <div class="table-scroll" tabindex="0" role="region" aria-label="BlasBench release results">
      <table class="lab-bench-table"><caption class="sr-only">Published Irish speech-recognition results</caption>
        <thead><tr><th scope="col">Model</th><th scope="col">WER</th><th scope="col">CER</th><th scope="col">Utterances</th><th scope="col">Evidence</th></tr></thead>
        <tbody id="blasbench-rows"></tbody>
      </table>
    </div>
    <p class="lab-note">Open a run’s details for source intervals. This table reflects the pinned release, not a comparison of current service configurations. No sample audio is republished.</p>
  </div>
</section>
"""


def _arena(pair: _ListeningPair | None) -> str:
    if pair:
        clips = "".join(
            f'<template class="lab-blind-clip" data-name="{escape(clip.voice)}" data-rights="{escape(clip.rights_url)}">'
            f'<audio controls preload="none" src="{escape(clip.audio_url)}"></audio></template>'
            for clip in pair.clips
        )
        return f"""
<section class="card lab-workspace" id="blind-round" aria-labelledby="blind-heading">
  <h2 id="blind-heading">Listen before you reveal the voices</h2>
  <p class="lab-studio-text" lang="ga">{escape(pair.text)}</p>
  <p><a href="{escape(pair.text_source)}">Sentence source</a></p>
  <p>Both voices read the same Irish sentence. This is a private comparison, not a vote: no preferences are uploaded.</p>
  {clips}
  <div class="lab-actions"><button type="button" class="lab-primary" id="start-listening" hidden>Start blind comparison</button></div>
  <noscript><p>JavaScript is required to randomize the voices.</p></noscript>
  <div id="blind-workspace" hidden>
    <div id="blind-tracks" class="lab-editor-grid"></div>
    <fieldset class="lab-listening" disabled><legend>Which sounds more natural?</legend>
      <label><input type="radio" name="natural" value="a"> Voice A</label>
      <label><input type="radio" name="natural" value="b"> Voice B</label>
      <label><input type="radio" name="natural" value="tie"> No preference</label>
    </fieldset>
    <fieldset class="lab-listening" disabled><legend>Which sounds more authentic to your ear?</legend>
      <label><input type="radio" name="dialect" value="a"> Voice A</label>
      <label><input type="radio" name="dialect" value="b"> Voice B</label>
      <label><input type="radio" name="dialect" value="tie"> No preference or unsure</label>
    </fieldset>
    <div class="lab-actions"><button type="button" id="reveal-voices" disabled>Reveal identities and rights</button></div>
    <ul id="blind-result" aria-label="Voice identities" hidden></ul>
    <p id="blind-status" class="lab-note" role="status"></p>
  </div>
</section>
"""
    return """
<div class="notice lab-notice"><strong>There is no public listening round.</strong>
<p>There are no cleared same-sentence A/B clips or public voting service. No votes are collected and no ratings are displayed.</p></div>
<details class="drill" open><summary><strong>What would a blind round measure?</strong></summary><div class="drill-body">
<p>Listeners hear two versions of the same sentence without knowing which system made either clip. Naturalness and dialect authenticity are judged separately, with the listener’s familiarity recorded alongside the ratings.</p>
<p>Preference is not a measure of word error rate, and an automatic score cannot establish which voice people prefer.</p>
</div></details>
<p class="lab-note"><a href="benchmarks.html">Explore published benchmark data</a> · <a href="speech.html">Check speech studio availability</a></p>
"""


def _developers() -> str:
    lookup = f"""
<section class="card lab-workspace" aria-labelledby="lookup-heading">
  <div class="lab-tool-head"><div><p class="eyebrow">OpenAPI · no key required</p><h2 id="lookup-heading">Try a dictionary lookup</h2></div>
    <a href="{BLAS}/tools/openapi.json">Read the OpenAPI schema</a></div>
  <form id="developer-lookup" class="lab-dev-lookup" action="{BLAS}/dictionary" method="get">
    <label for="lookup-query">Word or English meaning<input id="lookup-query" name="q" required maxlength="200" placeholder="Enter a lookup term"></label>
    <label for="lookup-language">Language<select id="lookup-language" name="language">
      <option value="irish">Irish</option><option value="welsh">Welsh</option><option value="scots-gaelic">Scottish Gaelic</option>
      <option value="breton">Breton</option><option value="cornish">Cornish</option><option value="manx">Manx</option>
    </select></label>
    <div class="lab-actions"><button type="submit" id="lookup-submit" class="lab-primary">Look up</button>
      <button type="button" id="lookup-download" disabled hidden>Download JSON</button></div>
  </form>
  <p class="lab-note" id="lookup-status" role="status">Only the lookup term and language are sent to Blas.</p>
  <ul id="lookup-results" class="lab-lookup-results" hidden></ul>
</section>
"""
    mcp_config = {
        "mcpServers": {"blas": {"type": "http", "url": f"{BLAS}/api/mcp"}},
    }
    return (
        lookup + '<div class="cards lab-cards">'
        + _card("OpenAPI", "Dictionary and pronunciation lookups, plus keyed transcription and gated translation.", f"{BLAS}/tools/openapi.json", "Read the OpenAPI schema")
        + _card("Model Context Protocol", "Blas’s remote MCP uses Streamable HTTP. The client guide covers tools, credentials and local setup.", f"{BLAS}/ai-instructions#language-tools", "Read the MCP client guide")
        + _card("Blas-IE recognition", "The public model card identifies the Irish speech-to-text weights as Apache-2.0. Check the model card before reuse.", MODEL_CARD, "Open the model card")
        + _card("Benchmark artifacts", "Inspect the Irish ASR harness and its published runs, or get six-language Teanga scores from this site.", "benchmarks.html", "Browse benchmark sources")
        + '</div><section class="card lab-workspace" aria-labelledby="mcp-endpoint"><h2 id="mcp-endpoint">Claude Code MCP configuration</h2>'
        + '<p>Save this as a project’s <code>.mcp.json</code> to connect over Streamable HTTP.</p>'
        + f'<pre><code id="mcp-config">{escape(json.dumps(mcp_config, indent=2))}</code></pre>'
        + '<div class="lab-actions"><button type="button" id="copy-mcp" hidden>Copy MCP configuration</button></div>'
        + '<p class="lab-note" id="mcp-copy-status" role="status"></p>'
        + '<p class="lab-note">Community transcription requires a key with <code>voice:transcribe</code>. '
        + 'Keep credentials in your client. Neither the example nor the lookup sends a key.</p></section>'
    )


def lab_pages(turnstile_site_key: str, arena_manifest: Path | None = None) -> list[_Page]:
    pair = _listening_pair(arena_manifest)
    pages = [
        _Page("lab", "Overview", LAB_TITLE, "Celtic speech, browser tools and reproducible benchmarks.", _overview()),
        _Page("speech", "Speech studio", "Open Celtic Speech Studio", "Explore public availability and rights for Irish, Welsh and Breton voices.", _speech(pair)),
        _Page("transcribe", "Transcribe", "Irish dictation & subtitles", "Record Irish speech or open a local media file, then edit and export subtitles.", _transcribe(turnstile_site_key), "transcribe.js"),
        _Page("write", "Proofing", "Writing & aural proofing", "Find Blas’s Irish and Welsh writing and mutation tools.", _proofing()),
        _Page("benchmarks", "Benchmarks", "Celtic language benchmarks", "Trace language-model and speech-recognition results to published evidence.", _benchmarks(), "benchmarks.js"),
        _Page("arena", "Blind listening", "Blind Voice Arena", "Explore how blind voice comparisons test naturalness and dialect authenticity.", _arena(pair), "arena.js" if pair else ""),
        _Page("developers", "Developers", "Open Lab for developers", "Try the Blas dictionary API and find public models, datasets and MCP documentation.", _developers(), "developers.js"),
    ]
    return [
        _Page(
            page.slug, page.label, page.title, page.description,
            '<nav class="lab-nav" aria-label="Open Lab"><ul>'
            + "".join(
                f'<li><a href="{item.slug}.html"'
                + (' aria-current="page"' if page.slug == item.slug else "")
                + f'>{item.label}</a></li>'
                for item in pages
            )
            + f'</ul></nav><div class="page-head"><p class="eyebrow">Blas research</p>'
            + f'<h1>{escape(page.title)}</h1><p class="lede">{escape(page.description)}</p></div>'
            + page.body,
            page.script,
        )
        for page in pages
    ]
