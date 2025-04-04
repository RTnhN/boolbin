# boolbin

Boolbin is a simple, boolean database. When you visit the page where it is hosted, [https://zstrout.pythonanywhere.com](https://zstrout.pythonanywhere.com), you will be given a write and read uuid. With the write uuid, you can set the bit to true or false. The read uuid then can read that state. You can also set an expiration or "gravity" time where the bit will be flipped back to false automatically. This can be helpful if you want to give or get the state of something without having to interface with a real db.   
