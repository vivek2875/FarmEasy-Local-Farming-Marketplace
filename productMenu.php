<?php
	session_start();
	require 'db.php';
?>
<!DOCTYPE html>
<html lang="en">
	<head>
		<meta charset="UTF-8">
		<title>FarmEasy</title>
		<meta http-equiv="content-type" content="text/html; charset=utf-8" />
		<meta name="description" content="" />
		<meta name="keywords" content="" />
		<link href="bootstrap/css/bootstrap.min.css" rel="stylesheet">
		<script src="https://ajax.googleapis.com/ajax/libs/jquery/1.12.4/jquery.min.js"></script>
        <script src="bootstrap/js/bootstrap.min.js"></script>
		<!--[if lte IE 8]><script src="css/ie/html5shiv.js"></script><![endif]-->
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
		<!--[if lte IE 8]><link rel="stylesheet" href="css/ie/v8.css" /><![endif]-->
	</head>
	<body>

		<?php
			require 'menu.php';
			function dataFilter($data)
			{
				$data = trim($data);
				$data = stripslashes($data);
				$data = htmlspecialchars($data);
				return $data;
			}
		?>

		<!-- One -->
			<section id="main" class="wrapper style1 align-center" >
				<div class="container">
						<h2>Welcome to DigiMart</h2>

				<?php
					if(isset($_GET['n']) && $_GET['n'] == 1):
				?>
					<h3>Select Filter</h3>
					<form method="GET" action="productMenu.php">
						<input type="hidden" value="1" name="n"/>
						<center>
							<div class="row">
								<div class="col-sm-4"></div>
								<div class="col-sm-2">
									<div class="select-wrapper" style="width: auto" >
										<select name="type" id="type" required style="background-color:white;color: black;">
											<option value="all" style="color: black;">List All</option>
											<option value="fruit" style="color: black;">Fruit</option>
											<option value="vegetable" style="color: black;">Vegetable</option>
											<option value="grain" style="color: black;">Grains</option>
										</select>
								  	</div>
								</div>
								<div class="col-sm-2">
									<input class="button special" type="submit" value="Go!" />
								</div>
								<div class="col-sm-4"></div>
							</div>
						</center>
					</form>
				<?php endif; ?>

				<section id="two" class="wrapper style2 align-center">
					<div class="container">
				<?php
					// Build SQL based on filter
					if(!isset($_GET['type']) || $_GET['type'] == "all") {
					 	$sql = "SELECT * FROM fproduct";
					} elseif(isset($_GET['type']) && $_GET['type'] == "fruit") {
						$sql = "SELECT * FROM fproduct WHERE pcat = 'Fruit'";
					} elseif(isset($_GET['type']) && $_GET['type'] == "vegetable") {
						$sql = "SELECT * FROM fproduct WHERE pcat = 'Vegetable'";
					} elseif(isset($_GET['type']) && $_GET['type'] == "grain") {
						$sql = "SELECT * FROM fproduct WHERE pcat = 'Grains'";
					} else {
                        // fallback
                        $sql = "SELECT * FROM fproduct";
                    }

					$result = mysqli_query($conn, $sql);
				?>
						<div class="row">
						<?php
							if ($result && mysqli_num_rows($result) > 0) {
								while($row = mysqli_fetch_assoc($result)):
									$picDestination = "images/productImages/".htmlspecialchars($row['pimage']);
						?>
									<div class="col-md-4">
										<section>
											<strong><b><h2 class="title" style="color:black;"><?php echo htmlspecialchars($row['product']); ?></h2></b></strong>

											<a href="review.php?pid=<?php echo urlencode($row['pid']); ?>">
												<img class="image fit" src="<?php echo $picDestination; ?>" height="220" />
											</a>

											<div style="text-align: left;">
												<blockquote>
													<?php echo "Type : ".htmlspecialchars($row['pcat']); ?><br>
													<?php echo "Price : Rs ".htmlspecialchars($row['price'])." /Kg"; ?><br>
												</blockquote>
											</div>
										</section>
									</div>
						<?php
								endwhile;
							} else {
								echo "<div class='col-12'><p>No products found.</p></div>";
							}
						?>
						</div> <!-- .row -->

					</div> <!-- .container -->
				</section> <!-- #two -->

				</div> <!-- .container -->
			</section> <!-- #main -->

	</body>
</html>
