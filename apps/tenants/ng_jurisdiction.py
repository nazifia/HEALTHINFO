"""Canonical Nigerian jurisdiction data: 36 states + FCT, 774 LGAs (INEC list).

Single source of truth for seeding the Jurisdiction tree. Used by the data
migration (0005) and available to tests/management commands. National root
name is COUNTRY; every state's LGAs are its INEC-recognised local governments.
"""

COUNTRY = "Nigeria"

# state -> list of LGAs. 774 LGAs total across 37 entries (36 states + FCT).
NG_STATES_LGAS = {
    "Abia": [
        "Aba North", "Aba South", "Arochukwu", "Bende", "Ikwuano",
        "Isiala Ngwa North", "Isiala Ngwa South", "Isuikwuato", "Obi Ngwa",
        "Ohafia", "Osisioma", "Ugwunagbo", "Ukwa East", "Ukwa West",
        "Umuahia North", "Umuahia South", "Umu Nneochi",
    ],
    "Adamawa": [
        "Demsa", "Fufore", "Ganye", "Girei", "Gombi", "Guyuk", "Hong", "Jada",
        "Lamurde", "Madagali", "Maiha", "Mayo-Belwa", "Michika", "Mubi North",
        "Mubi South", "Numan", "Shelleng", "Song", "Toungo", "Yola North",
        "Yola South",
    ],
    "Akwa Ibom": [
        "Abak", "Eastern Obolo", "Eket", "Esit Eket", "Essien Udim",
        "Etim Ekpo", "Etinan", "Ibeno", "Ibesikpo Asutan", "Ibiono-Ibom",
        "Ika", "Ikono", "Ikot Abasi", "Ikot Ekpene", "Ini", "Itu", "Mbo",
        "Mkpat-Enin", "Nsit-Atai", "Nsit-Ibom", "Nsit-Ubium", "Obot Akara",
        "Okobo", "Onna", "Oron", "Oruk Anam", "Udung-Uko", "Ukanafun",
        "Uruan", "Urue-Offong/Oruko", "Uyo",
    ],
    "Anambra": [
        "Aguata", "Anambra East", "Anambra West", "Anaocha", "Awka North",
        "Awka South", "Ayamelum", "Dunukofia", "Ekwusigo", "Idemili North",
        "Idemili South", "Ihiala", "Njikoka", "Nnewi North", "Nnewi South",
        "Ogbaru", "Onitsha North", "Onitsha South", "Orumba North",
        "Orumba South", "Oyi",
    ],
    "Bauchi": [
        "Alkaleri", "Bauchi", "Bogoro", "Damban", "Darazo", "Dass", "Gamawa",
        "Ganjuwa", "Giade", "Itas/Gadau", "Jama'are", "Katagum", "Kirfi",
        "Misau", "Ningi", "Shira", "Tafawa Balewa", "Toro", "Warji", "Zaki",
    ],
    "Bayelsa": [
        "Brass", "Ekeremor", "Kolokuma/Opokuma", "Nembe", "Ogbia", "Sagbama",
        "Southern Ijaw", "Yenagoa",
    ],
    "Benue": [
        "Ado", "Agatu", "Apa", "Buruku", "Gboko", "Guma", "Gwer East",
        "Gwer West", "Katsina-Ala", "Konshisha", "Kwande", "Logo", "Makurdi",
        "Obi", "Ogbadibo", "Ohimini", "Oju", "Okpokwu", "Otukpo", "Tarka",
        "Ukum", "Ushongo", "Vandeikya",
    ],
    "Borno": [
        "Abadam", "Askira/Uba", "Bama", "Bayo", "Biu", "Chibok", "Damboa",
        "Dikwa", "Gubio", "Guzamala", "Gwoza", "Hawul", "Jere", "Kaga",
        "Kala/Balge", "Konduga", "Kukawa", "Kwaya Kusar", "Mafa", "Magumeri",
        "Maiduguri", "Marte", "Mobbar", "Monguno", "Ngala", "Nganzai", "Shani",
    ],
    "Cross River": [
        "Abi", "Akamkpa", "Akpabuyo", "Bakassi", "Bekwarra", "Biase", "Boki",
        "Calabar Municipal", "Calabar South", "Etung", "Ikom", "Obanliku",
        "Obubra", "Obudu", "Odukpani", "Ogoja", "Yakurr", "Yala",
    ],
    "Delta": [
        "Aniocha North", "Aniocha South", "Bomadi", "Burutu", "Ethiope East",
        "Ethiope West", "Ika North East", "Ika South", "Isoko North",
        "Isoko South", "Ndokwa East", "Ndokwa West", "Okpe", "Oshimili North",
        "Oshimili South", "Patani", "Sapele", "Udu", "Ughelli North",
        "Ughelli South", "Ukwuani", "Uvwie", "Warri North", "Warri South",
        "Warri South West",
    ],
    "Ebonyi": [
        "Abakaliki", "Afikpo North", "Afikpo South", "Ebonyi", "Ezza North",
        "Ezza South", "Ikwo", "Ishielu", "Ivo", "Izzi", "Ohaozara",
        "Ohaukwu", "Onicha",
    ],
    "Edo": [
        "Akoko-Edo", "Egor", "Esan Central", "Esan North-East",
        "Esan South-East", "Esan West", "Etsako Central", "Etsako East",
        "Etsako West", "Igueben", "Ikpoba-Okha", "Oredo", "Orhionmwon",
        "Ovia North-East", "Ovia South-West", "Owan East", "Owan West",
        "Uhunmwonde",
    ],
    "Ekiti": [
        "Ado-Ekiti", "Efon", "Ekiti East", "Ekiti South-West", "Ekiti West",
        "Emure", "Gbonyin", "Ido-Osi", "Ijero", "Ikere", "Ikole", "Ilejemeje",
        "Irepodun/Ifelodun", "Ise/Orun", "Moba", "Oye",
    ],
    "Enugu": [
        "Aninri", "Awgu", "Enugu East", "Enugu North", "Enugu South",
        "Ezeagu", "Igbo Etiti", "Igbo Eze North", "Igbo Eze South", "Isi Uzo",
        "Nkanu East", "Nkanu West", "Nsukka", "Oji River", "Udenu", "Udi",
        "Uzo-Uwani",
    ],
    "Gombe": [
        "Akko", "Balanga", "Billiri", "Dukku", "Funakaye", "Gombe",
        "Kaltungo", "Kwami", "Nafada", "Shongom", "Yamaltu/Deba",
    ],
    "Imo": [
        "Aboh Mbaise", "Ahiazu Mbaise", "Ehime Mbano", "Ezinihitte",
        "Ideato North", "Ideato South", "Ihitte/Uboma", "Ikeduru",
        "Isiala Mbano", "Isu", "Mbaitoli", "Ngor Okpala", "Njaba", "Nkwerre",
        "Nwangele", "Obowo", "Oguta", "Ohaji/Egbema", "Okigwe", "Orlu",
        "Orsu", "Oru East", "Oru West", "Owerri Municipal", "Owerri North",
        "Owerri West", "Unuimo",
    ],
    "Jigawa": [
        "Auyo", "Babura", "Biriniwa", "Birnin Kudu", "Buji", "Dutse",
        "Gagarawa", "Garki", "Gumel", "Guri", "Gwaram", "Gwiwa", "Hadejia",
        "Jahun", "Kafin Hausa", "Kaugama", "Kazaure", "Kiri Kasama", "Kiyawa",
        "Maigatari", "Malam Madori", "Miga", "Ringim", "Roni",
        "Sule Tankarkar", "Taura", "Yankwashi",
    ],
    "Kaduna": [
        "Birnin Gwari", "Chikun", "Giwa", "Igabi", "Ikara", "Jaba", "Jema'a",
        "Kachia", "Kaduna North", "Kaduna South", "Kagarko", "Kajuru",
        "Kaura", "Kauru", "Kubau", "Kudan", "Lere", "Makarfi", "Sabon Gari",
        "Sanga", "Soba", "Zangon Kataf", "Zaria",
    ],
    "Kano": [
        "Ajingi", "Albasu", "Bagwai", "Bebeji", "Bichi", "Bunkure", "Dala",
        "Dambatta", "Dawakin Kudu", "Dawakin Tofa", "Doguwa", "Fagge",
        "Gabasawa", "Garko", "Garun Mallam", "Gaya", "Gezawa", "Gwale",
        "Gwarzo", "Kabo", "Kano Municipal", "Karaye", "Kibiya", "Kiru",
        "Kumbotso", "Kunchi", "Kura", "Madobi", "Makoda", "Minjibir",
        "Nasarawa", "Rano", "Rimin Gado", "Rogo", "Shanono", "Sumaila",
        "Takai", "Tarauni", "Tofa", "Tsanyawa", "Tudun Wada", "Ungogo",
        "Warawa", "Wudil",
    ],
    "Katsina": [
        "Bakori", "Batagarawa", "Batsari", "Baure", "Bindawa", "Charanchi",
        "Dandume", "Danja", "Dan Musa", "Daura", "Dutsi", "Dutsin-Ma",
        "Faskari", "Funtua", "Ingawa", "Jibia", "Kafur", "Kaita", "Kankara",
        "Kankia", "Katsina", "Kurfi", "Kusada", "Mai'Adua", "Malumfashi",
        "Mani", "Mashi", "Matazu", "Musawa", "Rimi", "Sabuwa", "Safana",
        "Sandamu", "Zango",
    ],
    "Kebbi": [
        "Aleiro", "Arewa Dandi", "Argungu", "Augie", "Bagudo", "Birnin Kebbi",
        "Bunza", "Dandi", "Fakai", "Gwandu", "Jega", "Kalgo", "Koko/Besse",
        "Maiyama", "Ngaski", "Sakaba", "Shanga", "Suru", "Wasagu/Danko",
        "Yauri", "Zuru",
    ],
    "Kogi": [
        "Adavi", "Ajaokuta", "Ankpa", "Bassa", "Dekina", "Ibaji", "Idah",
        "Igalamela-Odolu", "Ijumu", "Kabba/Bunu", "Kogi", "Lokoja",
        "Mopa-Muro", "Ofu", "Ogori/Magongo", "Okehi", "Okene", "Olamaboro",
        "Omala", "Yagba East", "Yagba West",
    ],
    "Kwara": [
        "Asa", "Baruten", "Edu", "Ekiti", "Ifelodun", "Ilorin East",
        "Ilorin South", "Ilorin West", "Irepodun", "Isin", "Kaiama", "Moro",
        "Offa", "Oke Ero", "Oyun", "Pategi",
    ],
    "Lagos": [
        "Agege", "Ajeromi-Ifelodun", "Alimosho", "Amuwo-Odofin", "Apapa",
        "Badagry", "Epe", "Eti-Osa", "Ibeju-Lekki", "Ifako-Ijaiye", "Ikeja",
        "Ikorodu", "Kosofe", "Lagos Island", "Lagos Mainland", "Mushin",
        "Ojo", "Oshodi-Isolo", "Shomolu", "Surulere",
    ],
    "Nasarawa": [
        "Akwanga", "Awe", "Doma", "Karu", "Keana", "Keffi", "Kokona", "Lafia",
        "Nasarawa", "Nasarawa Egon", "Obi", "Toto", "Wamba",
    ],
    "Niger": [
        "Agaie", "Agwara", "Bida", "Borgu", "Bosso", "Chanchaga", "Edati",
        "Gbako", "Gurara", "Katcha", "Kontagora", "Lapai", "Lavun", "Magama",
        "Mariga", "Mashegu", "Mokwa", "Munya", "Paikoro", "Rafi", "Rijau",
        "Shiroro", "Suleja", "Tafa", "Wushishi",
    ],
    "Ogun": [
        "Abeokuta North", "Abeokuta South", "Ado-Odo/Ota", "Yewa North",
        "Yewa South", "Ewekoro", "Ifo", "Ijebu East", "Ijebu North",
        "Ijebu North East", "Ijebu Ode", "Ikenne", "Imeko Afon", "Ipokia",
        "Obafemi Owode", "Odeda", "Odogbolu", "Ogun Waterside", "Remo North",
        "Sagamu",
    ],
    "Ondo": [
        "Akoko North-East", "Akoko North-West", "Akoko South-East",
        "Akoko South-West", "Akure North", "Akure South", "Ese Odo",
        "Idanre", "Ifedore", "Ilaje", "Ile Oluji/Okeigbo", "Irele", "Odigbo",
        "Okitipupa", "Ondo East", "Ondo West", "Ose", "Owo",
    ],
    "Osun": [
        "Aiyedaade", "Aiyedire", "Atakumosa East", "Atakumosa West",
        "Boluwaduro", "Boripe", "Ede North", "Ede South", "Egbedore",
        "Ejigbo", "Ife Central", "Ife East", "Ife North", "Ife South",
        "Ifedayo", "Ifelodun", "Ila", "Ilesa East", "Ilesa West", "Irepodun",
        "Irewole", "Isokan", "Iwo", "Obokun", "Odo Otin", "Ola Oluwa",
        "Olorunda", "Oriade", "Orolu", "Osogbo",
    ],
    "Oyo": [
        "Afijio", "Akinyele", "Atiba", "Atisbo", "Egbeda", "Ibadan North",
        "Ibadan North-East", "Ibadan North-West", "Ibadan South-East",
        "Ibadan South-West", "Ibarapa Central", "Ibarapa East",
        "Ibarapa North", "Ido", "Irepo", "Iseyin", "Itesiwaju", "Iwajowa",
        "Kajola", "Lagelu", "Ogbomosho North", "Ogbomosho South", "Ogo Oluwa",
        "Olorunsogo", "Oluyole", "Ona Ara", "Orelope", "Ori Ire", "Oyo East",
        "Oyo West", "Saki East", "Saki West", "Surulere",
    ],
    "Plateau": [
        "Barkin Ladi", "Bassa", "Bokkos", "Jos East", "Jos North", "Jos South",
        "Kanam", "Kanke", "Langtang North", "Langtang South", "Mangu",
        "Mikang", "Pankshin", "Qua'an Pan", "Riyom", "Shendam", "Wase",
    ],
    "Rivers": [
        "Abua/Odual", "Ahoada East", "Ahoada West", "Akuku-Toru", "Andoni",
        "Asari-Toru", "Bonny", "Degema", "Eleme", "Emohua", "Etche", "Gokana",
        "Ikwerre", "Khana", "Obio/Akpor", "Ogba/Egbema/Ndoni", "Ogu/Bolo",
        "Okrika", "Omuma", "Opobo/Nkoro", "Oyigbo", "Port Harcourt", "Tai",
    ],
    "Sokoto": [
        "Binji", "Bodinga", "Dange Shuni", "Gada", "Goronyo", "Gudu",
        "Gwadabawa", "Illela", "Isa", "Kebbe", "Kware", "Rabah", "Sabon Birni",
        "Shagari", "Silame", "Sokoto North", "Sokoto South", "Tambuwal",
        "Tangaza", "Tureta", "Wamako", "Wurno", "Yabo",
    ],
    "Taraba": [
        "Ardo-Kola", "Bali", "Donga", "Gashaka", "Gassol", "Ibi", "Jalingo",
        "Karim Lamido", "Kumi", "Lau", "Sardauna", "Takum", "Ussa", "Wukari",
        "Yorro", "Zing",
    ],
    "Yobe": [
        "Bade", "Bursari", "Damaturu", "Fika", "Fune", "Geidam", "Gujba",
        "Gulani", "Jakusko", "Karasuwa", "Machina", "Nangere", "Nguru",
        "Potiskum", "Tarmuwa", "Yunusari", "Yusufari",
    ],
    "Zamfara": [
        "Anka", "Bakura", "Birnin Magaji/Kiyaw", "Bukkuyum", "Bungudu",
        "Gummi", "Gusau", "Kaura Namoda", "Maradun", "Maru", "Shinkafi",
        "Talata Mafara", "Tsafe", "Zurmi",
    ],
    "Federal Capital Territory": [
        "Abaji", "Bwari", "Gwagwalada", "Kuje", "Kwali",
        "Municipal Area Council",
    ],
}


# Old / alternate names -> canonical name used above. Lets imports carrying
# legacy labels resolve to the seeded row. Keys are matched case-insensitively.
ALIASES = {
    "egbado north": "Yewa North",
    "egbado south": "Yewa South",
    "afikpo south (edda)": "Afikpo South",
    "edda": "Afikpo South",
    "amac": "Municipal Area Council",
    "abuja municipal": "Municipal Area Council",
    "abuja municipal area council": "Municipal Area Council",
    "fct": "Federal Capital Territory",
    "abuja": "Federal Capital Territory",
    "ogbomoso north": "Ogbomosho North",
    "ogbomoso south": "Ogbomosho South",
}


def canonical_name(name):
    """Map an alias (or already-canonical name) to the seeded canonical name."""
    return ALIASES.get(name.strip().lower(), name.strip())


def lga_count():
    return sum(len(v) for v in NG_STATES_LGAS.values())


# Guard the canonical count so an accidental edit can't silently ship a partial
# jurisdiction table. 36 states + FCT = 37; INEC recognises 774 LGAs.
assert len(NG_STATES_LGAS) == 37, len(NG_STATES_LGAS)
assert lga_count() == 774, lga_count()
