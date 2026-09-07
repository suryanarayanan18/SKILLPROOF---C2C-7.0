const { initializeApp, cert } = require("firebase-admin/app");
const { getFirestore } = require("firebase-admin/firestore");
const serviceAccount = require("./serviceAccountKey.json");

// Initialize the Firebase Admin SDK
initializeApp({
  credential: cert(serviceAccount)
});

const db = getFirestore();
console.log("Firebase connected successfully!");