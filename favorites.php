<?php
    session_start();
    require 'db.php';

    if(!isset($_SESSION['logged_in']) || $_SESSION['logged_in'] == 0){
        $_SESSION['message'] = "You need to first login to access this page !!!";
        header("Location: Login/error.php");
        exit();
    }

    $bid = $_SESSION['id'];

    // Add to favourites if flag exists
    if(isset($_GET['flag']) && isset($_GET['pid'])){
        $pid = $_GET['pid'];
        $sql = "INSERT INTO favorites (bid,pid) VALUES ('$bid', '$pid')";
        mysqli_query($conn, $sql);
    }
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>FarmEasy: Favourites</title>
    <meta http-equiv="content-type" content="text/html; charset=utf-8" />
    <link href="bootstrap/css/bootstrap.min.css" rel="stylesheet">

    <script src="https://ajax.googleapis.com/ajax/libs/jquery/1.12.4/jquery.min.js"></script>
    <script src="bootstrap/js/bootstrap.min.js"></script>

    <link rel="stylesheet" href="login.css"/>
    <script src="js/jquery.min.js"></script>
    <script src="js/skel.min.js"></script>
    <script src="js/skel-layers.min.js"></script>
    <script src="js/init.js"></script>

    <noscript>
        <link rel="stylesheet" href="css/skel.css" />
        <link rel="stylesheet" href="css/style.css" />
        <link rel="stylesheet" href="css/style-xlarge.css" />
    </noscript>
</head>
<body>

<?php require 'menu.php'; ?>

<section id="main" class="wrapper style1 align-center">
    <div class="container">
        <h2>Favourites</h2>

        <section id="two" class="wrapper style2 align-center">
            <div class="container">
                <div class="row">

                <?php
                    $sql = "SELECT * FROM favorites WHERE bid = '$bid'";
                    $result = mysqli_query($conn, $sql);

                    if($result && mysqli_num_rows($result) > 0){
                        while($row = mysqli_fetch_assoc($result)){
                            $pid = $row['pid'];

                            $productQuery = mysqli_query($conn, "SELECT * FROM fproduct WHERE pid='$pid'");
                            if($productQuery && mysqli_num_rows($productQuery) > 0){
                                $row1 = mysqli_fetch_assoc($productQuery);
                                $pic = "images/productImages/".$row1['pimage'];
                ?>

                    <div class="col-md-4">
                        <section>
                            <strong><h3 style="color:black;"><?php echo htmlspecialchars($row1['product']); ?></h3></strong>

                            <a href="review.php?pid=<?php echo urlencode($row1['pid']); ?>">
                                <img class="image fit" src="<?php echo $pic; ?>" alt="product image" />
                            </a>

                            <div style="text-align:left;">
                                <blockquote>
                                    <?php echo "Type : ".htmlspecialchars($row1['pcat']); ?><br>
                                    <?php echo "Price : ".htmlspecialchars($row1['price'])." /-"; ?><br>
                                </blockquote>
                            </div>
                        </section>
                    </div>

                <?php
                            }
                        }
                    } else {
                        echo "<h3>No Favourite Items Yet!</h3>";
                    }
                ?>

                </div>
            </div>
        </section>
    </div>
</section>

</body>
</html>
