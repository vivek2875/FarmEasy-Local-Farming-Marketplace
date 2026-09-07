<?php
    session_start();
    require 'db.php';

    // Check login session
    if(!isset($_SESSION['Name'])){
        die("Error: You must be logged in to submit a review.");
    }

    $rating = isset($_POST['rating']) ? intval($_POST['rating']) : 0;
    $review = isset($_POST['comment']) ? trim($_POST['comment']) : "";
    $name = $_SESSION['Name'];
    $pid = isset($_GET['pid']) ? intval($_GET['pid']) : 0;

    // Basic validation
    if($pid == 0){
        die("Product ID missing.");
    }
    if($rating < 0 || $rating > 10){
        die("Invalid rating. Must be between 0 to 10.");
    }
    if(empty($review)){
        die("Review cannot be empty.");
    }

    $sql = "INSERT INTO review (pid, name, rating, comment)
            VALUES ('$pid', '$name', '$rating', '$review')";

    $result = mysqli_query($conn, $sql);

    if(!$result){
        echo "Database Error: " . mysqli_error($conn);
    } else {
        header("Location: review.php?pid=".$pid);
        exit;
    }
?>
