"""Bundled protection vocabulary for the local diagnostics engine.

The spelling checker only knows an American-English dictionary of common words.
Academic writing is full of words that dictionary does not contain — names,
caste and community terms, place names, field concepts and abbreviations — and
correcting those is the classic false positive that makes a writer switch a
checker off for good. This module is the curated list the engine consults
*before* the dictionary, plus the structural rules that protect words the list
cannot know about.

Three points about scope, so the guarantee is not overstated:

* a word that is protected is never reported as a spelling problem, but the
  other rule families (agreement, punctuation, style) still apply to it;
* the list is deliberately a *starting point*, not an ontology: the personal
  dictionary in the workspace remains the way a researcher protects the exact
  vocabulary of their own project, and it always wins;
* protection is one-directional and conservative. Missing a real typo is a
  smaller failure than rewriting a researcher's caste term or a village name.

Sources for the vocabulary: the terms are the ordinary English-language
spellings used in Indian social-science writing and in Government of India
statistical publications (Census of India, NSS/NFHS reports, the Scheduled
Castes and Scheduled Tribes lists, Ministry of Statistics nomenclature). Where
a term has several accepted spellings, all of them are listed.
"""

from __future__ import annotations

# Names that appear constantly in South Asian academic prose (authors,
# acknowledgements, interview participants). Given names only — surnames are
# covered by the structural rules and the personal dictionary.
SOUTH_ASIAN_NAMES = frozenset(
    """
    aarav aarti abdul aditi aditya advait aishwarya ajay akash akhilesh akhtar
    alok aman amartya amit amita amol amrita anand ananya anil anita anjal
    anjali ankit anshu anuradha aparna arjun arnab arun aruna asha ashok ashwin
    asif avinash ayush azad babasaheb bharat bhavna bhavesh biju bimal bipin
    chandan chandni chetan chinmay darshan deepa deepak devi devika dhananjay
    dharmendra dilip divya farhan farida ganesh gargi gauri gayatri geeta gopal
    gourish gowda gurpreet harish harpreet hemant hina iffat ila imran indira
    iqbal irfan ishaan jaya jayant jayesh jigna jitendra jyoti kabir kalpana
    kamal kamala kanaka kavita kavya khushbu kiran kishore krishna lakshmi
    lalita latha lokesh madhav madhu mahananda mahesh maithili malini mamata
    manish manoj manu mary maya meena meenakshi meera mohammad mohammed mohan
    mona mridula mukesh mukul muna munira nabanita nadia nagaraj namrata
    nandini nandita naresh narayan nasreen naveen neha nikhil nilesh nirmala
    nisha nitin padmini pallavi pandurang paras pardeep parul pavan pooja
    prabhu pradyumna prakash pramod pranav prasad prashant pratik praveen
    priya priyanka puja puneet pushpa raghav raj rajan rajani rajesh rajiv
    rajni rakhi ramesh ramya rani ranjit rashmi ratna ravi rekha renuka riya
    rohan rohit rupa rupali sabina sadhana sahil saisalil sajid sameer sandeep
    sandhya sanjay sanjeev santosh sanya saraswati sarfaraz sarita satish
    satnam saurabh savita seema sehnaz shabana shahid shaheen shaista shalini
    shankar shanta sharad shashi shazia sheetal shirish shiv shobha shreya
    shridhar shweta siddharth sikandar sneha somnath sonam sonia sridevi
    srikanth sudha sudhir suhas sujata sukhdev suman sumitra sunil sunita
    suresh surya suzanne swati tara tarun tejas thangam thanjavur tilak
    trisha tulsi uma umesh upendra usha uttam varun vasanth vandana varsha
    venkatesh vidya vijay vijaya vikram vinay vinod vipin vishal vishnu vivek
    waman yamini yash yashodha yasmin yogesh yusuf zainab zara zoya
    """.split()
)

# Caste, tribe, community and kinship terminology as used in scholarly and
# official Indian usage. These are fields of study, not errors.
COMMUNITY_TERMS = frozenset(
    """
    adivasi adivasis ambedkarite ambedkarism antyaja bahujan balutedar baluta
    biradari biradaris brahmin brahmins brahminical chamar chamars cheri
    cheris dalit dalits dalitbahujan devadasi devadasis dhobi dhobis dubla
    dublas ezhava ezhavas gond gonds gotra gotras gujjar gujjars harijan
    harijans holer holers jajmani jati jatis jat jatav jatavs jhuggi jhuggis
    kammas kapu kapus karanam karnam khap khaps khandan khandans kharwar
    kolam kori koris koya koyas kshatriya kshatriyas kudumbi kudumbis kumhar
    kumhars kurmi kurmis lingayat lingayats madiga madigas mahar mahars mala
    malas mali malis mappila mappilas maratha marathas meena meenas mudaliar
    mudaliars nadar nadars nair nairs namasudra namasudras nayaka nayakas
    panchayat panchayats paraiyar paraiyars patel patels patidar patidars
    pulaya pulayas rajbansi rajpurohit rajpurohits reddy reddys sahara
    saharao savarna savarnas shudra shudras sikh sikhs siraiki sunni sunnis
    thevar thevars thiyya thiyyas thiyyar thiyyars toda todas vaisya
    vaishya vaishyas vannan vannans vanniakula vanniakulas velama velamas
    vokkaliga vokkaligas warli warlis yadav yadavs
    """.split()
)

# Places that recur in Indian research writing: states, major cities, districts
# that appear in field studies, rivers, and physiographic regions.
PLACE_NAMES = frozenset(
    """
    agra ahmedabad aizawl ajmer alappuzha aligarh allahabad alwar amaravati
    amritsar anand anantapur anantnag araria arunachal assam aurangabad
    ayyampettai bagalkot baghpat bahraich balaghat balangir ballari balrampur
    banswara bardhaman bareilly barpeta bastar bathinda begusarai belagavi
    bengaluru bettiah bhadrak bhagalpur bhandara bharatpur bharuch bhavnagar
    bhilwara bhind bhojpur bhopal bhubaneswar bidar bihar bijapur bikaner
    bilaspur birbhum bokaro budaun bulandshahr buldhana bundelkhand burdwan
    chamarajanagar champawat chandauli chandigarh chandrapur chennai
    chhatarpur chhattisgarh chhindwara chikkaballapur chikkamagaluru
    chitradurga chitrakoot chittoor churu coimbatore coorg cuttack dadra
    dakshina davanagere deccan dehradun delhi dhanbad dhar dharwad dhaulpur
    dhubri dindigul dindori doab dumka durgapur dwarka ernakulam ettawah
    faizabad faridabad farrukhabad fatehabad fatehpur fazilka gandhinagar
    ganga gangtok gaya ghaziabad giridih goa godavari golaghat gonda gondia
    gopalganj gorakhpur greater guntur gurugram guwahati gwalior hajipur
    hampi hanumangarh hapur harda hardoi haridwar hassan hathras haveri
    hazaribagh himachal hindupur hisar hubballi hyderabad ichalkaranji imphal
    indore itanagar jabalpur jagatsinghpur jaisalmer jaipur jajpur jalandhar
    jalgaon jalna jalpaiguri jammu jamnagar jamshedpur jamui jangaon
    jashpur jaunpur jehanabad jhabua jhajjar jhalawar jhansi jhargram
    jharkhand jhunjhunu jind jodhpur jorhat junagadh kadapa kaimur kaithal
    kalahandi kalaburagi kalimpong kallakurichi kamrup kanchipuram kandhamal
    kangra kanhangad kannauj kannur kanpur kanyakumari kapurthala karaikal
    karaikudi karimnagar karnal karnataka karur kasaragod kathua katihar
    kaveri kendrapara kendujhar khagaria khammam khandwa khargone kheda
    khordha khowai kishanganj kishtwar kochi kohima kokrajhar kolar kolhapur
    kolkata kollam kollidam koppal koraput korba kota kottayam kozhikode
    krishna krishnagiri kulgam kumbakonam kurnool kurukshetra kutch ladakh
    lakhimpur lakhisarai lalitpur latehar latur lawngtlai leh lucknow
    ludhiana lunglei madhepura madhubani madhya madurai mahabubnagar
    maharajganj maharashtra mahasamund mahbubnagar mahe mahendragarh
    mahoba mainpuri malappuram malkangiri malnad malout mandi mandla
    mandsaur mango manipal mansa marigaon mathura mau mavelikkara mayurbhanj
    medak meerut meghalaya mirzapur mizoram moradabad morena mumbai munger
    murshidabad muzaffarnagar muzaffarpur mysuru nabrangpur nadia nagaon
    nagaland nagapattinam nagaur nagpur nainital nalanda nalbari nalgonda
    namakkal nanded nandurbar narayanpur narmada narnaul narsinghpur
    nashik navsari nawada nayagarh neemuch nellore nicobar nilgiris
    nizamabad noney nohradiha north nowgong nuapada odisha osmanabad
    pakur palakkad palamu palghar pali palwal panchkula panipat panna
    panvel paradip parbhani pathanamthitta pathankot patiala patna pauri
    perambalur peren pithoragarh ponnani porbandar prakasham puducherry
    pune purba puri purnea pursurah pushkar puthukkottai rae raibareli
    raichur raigad raigarh raisen rajanna rajgarh rajkot rajouri rajsamman
    rajshahi ramanathapuram ramban ramgarh rampur ranchi rangareddy
    ratlam ratnagiri raurkela rayalaseema reasi rewa rewari rohtak rohtas
    rudraprayag rupnagar saharanpur saharsa sahibganj salem samastipur
    sambalpur sambhal sangam sangli sangrur sant santal saran saraikela
    sarkeguda sasaram satara satna sawai secunderabad sehore seoni
    serchhip shahjahanpur shajapur shakti shamil shikohabad shillong
    shimla shimoga shivpuri sholapur shopian shravasti sikar sikkim
    sindhudurg singrauli sirmaur sirohi sitamarhi sitapur sivaganga
    sivakasi siwan solan solapur sonbhadra sonipat south srikakulam
    srinagar subarnapur sugarcane supaul surendranagar surgu sultanpur
    sundargarh supur surajpur surat surguja tamenglong tamil tandur
    tanjavur tarn taran tawang tehri telangana tenkasi tezpur thane
    thanjavur theni thiruvananthapuram thoothukudi thoubal thrissur tikamgarh
    tiruchirappalli tirunelveli tirupati tiruppur tiruvallur tiruvannamalai
    tiruvarur tonk tripura tumakuru tunga tungabhadra tuensang udaipur
    udalguri udham udupi ujjain ukhrul ulhasnagar una unakoti unnao uppal
    uttar uttarakhand uttarkashi vadodara vaishali valsad vapi varanasi
    vellore veraval vidarbha vidisha vijayapura vijayawada vikarabad
    villupuram viluppuram virudhunagar visakhapatnam vizianagaram wanaparthy
    warangal wardha washim wayanad west yadgir yamuna yamunanagar yanam
    yavatmal yavatmal yelahanka zunheboto
    """.split()
)

# Field concepts, institutions, programmes and schemes that a general English
# dictionary does not contain but that academic writing uses as ordinary nouns.
FIELD_CONCEPTS = frozenset(
    """
    adivasi adivasis agri agribusiness agro agroecology algocracy anthropos
    ascriptive ashram ashrams ayacut ayacuts bandh bandhs bhoodan
    chowk chowks chulha chulhas creche creches crore crores dalit dalits
    devadasi devadasis dharamshala dharamshalas dharma dipankar elaka elakas
    fasal firka firkas gherao gheraos gram gramam grameen gurukul gurukuls
    haat haats harijan harijans indigo jajmani jatha jathas jati jatis
    kalari katchi katchis kharif khasra khasras khata khatas kisan kisans
    kotwal kutcha lakh lakhs lakhpati madrasa madrasas mahal mahals
    mahila mahilas maktab mandal mandals mandi mandis manor manors
    mathadi mathadis mazdoor mela melas mohalla mohallas moksha mudaliar
    namboothiri naxal naxalite naxals neem nyaya ooran ombudsman
    oppidan panchayat panchayati patta pattas patwari patwaris
    pirivu pirivus podu podus powindah pronoia rabi raiyat raiyati
    raiyats ramzan ryot ryots ryotwari ryots sabha sabhas salwa panchayat
    santhal sarpanch sarpanches sarvodaya satyagraha satyagrahis sawarna
    shramdan shramik sramik swaraj swarajya taluk taluks taluka talukas
    tehsil tehsildar tehsildars tehsils thana thanas thikana thikanas
    tola tolas tonga ultapani varna varnas vatan vatans waqf wakf zamindar
    zamindari zamindars jagirdar jagirdars jagir jagirs bhumidar khatedar
    ryotwari mahalwari khoti pattidari mirasi rayon rajbari
    """.split()
)

# Abbreviations, survey names and statistical vocabulary an academic paper
# uses without ever spelling them out.
RESEARCH_ABBREVIATIONS = frozenset(
    """
    anova ancova anova ancov anc rdd did iv ols gmm probit logit
    sc st obc obcs nss nsso nfhs nfhs-irbid mospi csds lokniti
    ncer ncaer icrisat igidr jnu du isi cpr tiss iit iim iisc ignou
    irdp cmie aidds sdg sdgs gdp gva hdi ihds wtc gini ppp
    unescoundp who unicef unep fao ilo undp unaids worldbank
    irdb irb doi url urn isbn issn apa mla chicago mla
    rt pcr ngo ngos shg shgs cbo cbos prifashgs psus
    fdi gdp oda ngo cso csos cds crsp
    """.split()
)


def protected_words() -> frozenset[str]:
    """Every bundled word the spelling checker must leave alone (lower-cased)."""
    return (
        SOUTH_ASIAN_NAMES
        | COMMUNITY_TERMS
        | PLACE_NAMES
        | FIELD_CONCEPTS
        | RESEARCH_ABBREVIATIONS
    )


PROTECTED_WORDS = protected_words()

# Suffixes that mark a token as a South Asian place, community or institution
# name rather than a misspelling, used when the exact word is not in the lists.
PROTECTED_SUFFIXES = (
    "pura", "puram", "patnam", "pattanam", "palli", "halli", "kere", "kuppam",
    "wadi", "wada", "nagar", "giri", "gudem", "garh", "pur", "ganj", "bad",
    "abad", "konda", "peta", "palle", "guda", "pura", "pura",
)

PROTECTED_PREFIXES = (
    "sri", "shri", "smt", "dr", "prof", "shrimati",
)

def looks_like_acronym(token: str) -> bool:
    """True for tokens shaped like an abbreviation rather than a word.

    Two or more capital letters, optionally separated by dots or slashes, or a
    short all-capital run, or a token that mixes digits with letters the way
    scheme and survey names do ("NFHS-5", "NSS-68", "MDG-4").
    """
    if not token:
        return False
    stripped = token.strip(".,;:()[]/")
    if not stripped:
        return False
    if len(stripped) <= 6 and stripped.isupper() and any(c.isalpha() for c in stripped):
        return True
    if any(c.isdigit() for c in stripped) and any(c.isalpha() for c in stripped):
        return True
    # "S.C.", "M.A.", "Ph.D." — capital letters separated by periods
    if stripped.count(".") >= 1:
        letters = [part for part in stripped.split(".") if part]
        if letters and all(len(part) <= 3 and part[:1].isupper() for part in letters):
            return True
    # "MoSPI", "NSSO"-style internal capitals
    if len(stripped) >= 3 and stripped[0].isupper() and any(c.isupper() for c in stripped[1:]):
        if stripped[1:].islower() and stripped[:1].isupper():
            return False  # "Karnataka" is not an acronym
        return any(c.isupper() for c in stripped[1:])
    return False


def is_protected_word(word: str, *, capitalized: bool = False) -> bool:
    """True when a lower-cased word is in the bundled protection vocabulary.

    The suffix rule only applies to a capitalised token: place-name endings
    ("-pura", "-halli", "-nagar") would otherwise hide ordinary misspellings
    that happen to end in the same letters.
    """
    if word in PROTECTED_WORDS:
        return True
    if capitalized and len(word) > 4:
        for suffix in PROTECTED_SUFFIXES:
            if word.endswith(suffix):
                return True
    return False
