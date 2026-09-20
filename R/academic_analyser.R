AcademicAnalyzer <- function(long_sentence_words = 35L) {
  if (length(long_sentence_words) != 1L || long_sentence_words < 1) stop("long_sentence_words must be positive")

  formulaic <- c("it is important to note that","it is worth noting that","it should be noted that",
    "in today's world","in the modern era","in the realm of","a plethora of","plays a crucial role in",
    "plays a vital role in","delve into","deep dive into","shed light on")
  absolutes <- c("always","never","proves that","clearly demonstrates","definitively shows","undeniable","unquestionably")
  comparison <- c("however","whereas","although","by contrast","in contrast","similarly","likewise","unlike","while","yet")
  evidence <- c("according to","finds","found","reports","reported","documents","documented","observes","observed",
    "estimates","estimated","survey","interview","data","evidence")
  interpretation <- c("this suggests","this indicates","this means","this demonstrates","this reveals",
    "therefore","thus","hence","because")
  gap <- c("however, few","however, little","remains unclear","remains underexplored","limited attention",
    "little attention","has not examined","has received little","gap in the literature","underexplored")
  contribution <- c("this study","this research","the present study","this paper","this article","i argue","i examine","i explore")

  esc <- function(x) gsub("([][{}()+*^$|\\\\?.])", "\\\\\1", x, perl=TRUE)
  words <- function(x) {
    z <- gregexpr("\\b[[:alnum:]_'-]+\\b", tolower(x), perl=TRUE)
    y <- regmatches(x,z)[[1]]
    if (length(y)==1L && identical(y,character(0))) character(0) else y
  }
  sentences <- function(x) {
    x <- trimws(x); if (!nzchar(x)) return(character(0))
    y <- unlist(strsplit(x,"(?<=[.!?])\\s+",perl=TRUE),use.names=FALSE)
    trimws(y[nzchar(trimws(y))])
  }
  contains <- function(s, sig) sig[vapply(sig,function(p) grepl(paste0("\\b",esc(p),"\\b"),tolower(s),perl=TRUE),logical(1))]

  citations <- function(x) {
    out <- character(0)
    z <- gregexpr("\\b[A-Z][A-Za-z'’-]+(?:\\s+et al\\.)?\\s*\\((?:19|20)[0-9]{2}[a-z]?\\)",x,perl=TRUE)
    a <- regmatches(x,z)[[1]]
    if(length(a) && !identical(a,character(0))) out <- c(out,a)
    z <- gregexpr("\\([^()]*?(?:19|20)[0-9]{2}[a-z]?[^()]*?\\)",x,perl=TRUE)
    p <- regmatches(x,z)[[1]]
    if(length(p) && !identical(p,character(0))) for(item in p) {
      z2 <- gregexpr("[A-Z][A-Za-z'’-]+(?:\\s+et al\\.)?,?\\s+(?:19|20)[0-9]{2}[a-z]?",item,perl=TRUE)
      a2 <- regmatches(item,z2)[[1]]
      if(length(a2) && !identical(a2,character(0))) out <- c(out,trimws(a2))
    }
    unique(out)
  }
  has_citation <- function(x) length(citations(x)) > 0L
  source_attr <- function(s) has_citation(s) || grepl("\\b(?:according to|argues?|argue|finds?|found|shows?|show|reports?|reported|documents?|documented|observes?|observed|estimates?|estimated)\\b",s,ignore.case=TRUE,perl=TRUE)

  analyse <- function(text) {
    if(!is.character(text) || length(text)!=1L) stop("text must be a single character string")
    ss <- sentences(text)
    roles <- lapply(seq_along(ss),function(i) {
      s <- ss[[i]]; ev <- contains(s,evidence); it <- contains(s,interpretation); co <- contains(s,comparison)
      ga <- contains(s,gap); cn <- contains(s,contribution); ct <- has_citation(s)
      role <- if(length(ga)) "gap" else if(length(co)) "comparison_or_synthesis" else if(length(ev)||ct) "source_or_evidence"
        else if(length(it)) "interpretation" else if(length(cn)) "author_position" else "claim_or_context"
      list(sentence=i,role=role,signals=list(citation=ct,evidence=ev,interpretation=it,comparison=co,gap=ga,contribution=cn),text=s)
    })
    rn <- if(length(roles)) vapply(roles,function(x)x$role,character(1)) else character(0)
    req <- c("source_or_evidence","interpretation","comparison_or_synthesis")
    op <- vapply(ss,function(s){w<-words(s);if(length(w))paste(head(w,2),collapse=" ")else""},character(1))
    tab <- table(op[nzchar(op)]); rep <- tab[tab>1]
    rep_out <- as.list(as.integer(rep)); if(length(rep_out)) names(rep_out)<-names(rep)
    long <- lapply(seq_along(ss),function(i){n<-length(words(ss[[i]]));if(n>=long_sentence_words)list(sentence=i,words=n,text=ss[[i]])else NULL})
    long <- Filter(Negate(is.null),long)
    cited <- which(vapply(ss,function(s)source_attr(s)&&has_citation(s),logical(1)))
    uncited <- which(vapply(ss,function(s)source_attr(s)&&!has_citation(s),logical(1)))
    list(sentence_count=length(ss),word_count=length(words(text)),
      formulaic_phrases=formulaic[vapply(formulaic,function(p)grepl(esc(p),tolower(text),perl=TRUE),logical(1))],
      possible_overclaims=absolutes[vapply(absolutes,function(p)grepl(esc(p),tolower(text),perl=TRUE),logical(1))],
      repetitive_openings=rep_out,long_sentences=long,citation_count=length(citations(text)),citations=citations(text),
      citation_diagnostics=list(cited_source_claims=length(cited),possible_uncited_source_claims=uncited,
        note="Possible flags only; some claims may be common knowledge or supported by a citation elsewhere in the paragraph."),
      roles=roles,literature_review_signals=list(source_or_evidence="source_or_evidence"%in%rn,
        interpretation="interpretation"%in%rn,comparison_or_synthesis="comparison_or_synthesis"%in%rn,
        gap="gap"%in%rn,author_position="author_position"%in%rn,possible_missing=req[!req%in%rn]))
  }
  summary <- function(text) {
    r<-analyse(text); m<-sprintf("%d sentences, %d words.",r$sentence_count,r$word_count)
    if(length(r$formulaic_phrases))m<-c(m,paste0("Formulaic phrasing: ",paste(r$formulaic_phrases,collapse=", " ),"."))
    if(length(r$possible_overclaims))m<-c(m,paste0("Possible overclaiming: ",paste(r$possible_overclaims,collapse=", " ),"."))
    if(length(r$citation_diagnostics$possible_uncited_source_claims))m<-c(m,paste0("Possible uncited source-based claims in sentence(s): ",paste(r$citation_diagnostics$possible_uncited_source_claims,collapse=", " ),"."))
    paste(m,collapse="\\n")
  }
  list(analyse=analyse,summary=summary,sentences=sentences,citations=citations)
}
