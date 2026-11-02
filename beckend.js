let currentSessionId = null;

// 1. Telegram orqali kod so'rash
async function sendSmsCode() {
    const rawPhone = document.getElementById('regPhone').value.trim();
    if (rawPhone.length < 9) {
        alert("Iltimos, telefon raqamingizni to'liq kiriting!");
        return;
    }

    currentSessionId = "session_" + Date.now() + "_" + Math.floor(Math.random() * 1000);

    try {
        const response = await fetch("http://localhost:8000/api/request-code", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ session_id: currentSessionId })
        });
        
        const data = await response.json();
        
        // Telegram Bot havolasini yangi oynada ochish
        window.open(data.bot_link, '_blank');
        
        document.getElementById('targetPhoneDisplay').innerText = "+998 " + rawPhone;
        document.getElementById('regStep1').classList.add('hidden');
        document.getElementById('regStep2').classList.remove('hidden');

        alert("Telegram bota o'tib, /start tugmasini bosing hamda kanallarga obuna bo'lib kodni oling!");
    } catch (err) {
        alert("Server bilan bog'lanishda xatolik yuz berdi!");
    }
}

// 2. Kiritilgan kodni tekshirish
async function verifySmsCode() {
    let enteredCode = "";
    document.querySelectorAll('.otp-input').forEach(input => enteredCode += input.value);

    if (enteredCode.length < 4) {
        alert("Iltimos, 4 xonali kodni to'liq kiriting!");
        return;
    }

    try {
        const response = await fetch("http://localhost:8000/api/verify-code", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ 
                session_id: currentSessionId, 
                code: enteredCode 
            })
        });

        if (response.ok) {
            document.getElementById('smsErrorAlert').classList.add('hidden');
            document.getElementById('regStep2').classList.add('hidden');
            document.getElementById('regStep3').classList.remove('hidden');
        } else {
            document.getElementById('smsErrorAlert').classList.remove('hidden');
        }
    } catch (err) {
        alert("Xatolik yuz berdi!");
    }
}